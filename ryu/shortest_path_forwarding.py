'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN-WIFI/ryu/shortest_path_forwarding.py
Date: 2023-07-08 09:59:13
Description: 
'''
import time

from ryu.base import app_manager
from ryu.base.app_manager import  lookup_service_brick
from ryu.ofproto import ofproto_v1_3
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls, MAIN_DISPATCHER, DEAD_DISPATCHER, CONFIG_DISPATCHER
from ryu.lib import hub
from ryu.lib.packet import packet
from ryu.lib.packet import arp, ipv4, ethernet

from pathlib import Path
import pickle

import setting
# import network_structure
# import network_monitor
# import network_delay
import networkx as nx

class ShortestPathForwarding(app_manager.RyuApp):
    OFP_VERSION = [ofproto_v1_3.OFP_VERSION]
    # _CONTEXTS = {
    #     'discovery': network_structure.NetworkStructure,
    #     'monitor': network_monitor.NetworkMonitor,
    #     'detector': network_delay.NetworkDelayDetector
    # }

    def __init__(self, *args, **kwargs):
        super(ShortestPathForwarding, self).__init__(*args, **kwargs)
        self.discovery = lookup_service_brick('discovery')
        self.monitor = lookup_service_brick('monitor')
        self.detector = lookup_service_brick('detector')
        self.name = 'shortest_path_forwarding'
        self.pickle_dir = '/home/jjj/Desktop/SDN-WIFI/ryu/weight/topo34'
        self.court = 0

        self.shortest_thread = hub.spawn(self.super_schedule)


    def super_schedule(self):
        hub.sleep(10)
        num = 1
        while True:
            print('-----------  court = {} '.format(self.court))
            if self.court == 30 : 
                print('-----------    300s后开始采集数据')       
                self.shortest_thread = hub.spawn(300)     
                print('-----------    10s后开始采集数据')  
                self.shortest_thread = hub.spawn(10)     

            self.discovery.scheduler()
            self.monitor.scheduler()
            self.detector.scheduler()

            if self.court >= 30:
                self.save_pickle_graph(num)
                print('###########   {}  采集成功'.format(num))   
                num += 1
            self.court += 1


            hub.sleep(setting.SCHEDULE_PERIOD)
   

    def save_pickle_graph(self, num):
        """
            保存图信息的pkl文件
            ./pkl/now_time/name.pkl
        """
        name = f"{num}-" + time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
        _path = self.pickle_dir / Path(name + '.pkl')
        _graph = self.discovery.graph.copy()
        nx.write_gpickle(_graph, _path)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # print(" --- shortest ---> PacketIn")
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)

        arp_pkt = pkt.get_protocol(arp.arp)
        ipv4_pkt = pkt.get_protocol(ipv4.ipv4)
        ethernet_pkt=pkt.get_protocols(ethernet.ethernet)

        if isinstance(ipv4_pkt, ipv4.ipv4):
            print(" --- shortest --->===> IPv4 processing")
            if len(ethernet_pkt):
                eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
                print(" --- shortest --->===> calculate shortest path ===>")
                self.calculate_shortest_paths(msg, eth_type, ipv4_pkt.src, ipv4_pkt.dst)

    def calculate_shortest_paths(self, msg, eth_type, src_ip, dst_ip):
        """ 根据消息计算最短路径"""
        datapath = msg.datapath
        in_port = msg.match['in_port']

        # ------------------------ dpid映射处理 -----------------------------------
        dpid = self.discovery.original_2_map_switch_id_dict.get(datapath.id)
        # -------------------------------------------------------------------------

        # 1. 找出位置
        src_dst_switches = self.get_switches(dpid, in_port, src_ip, dst_ip)
        if src_dst_switches:
            src_switch, dst_switch = src_dst_switches
            if dst_switch:
                # 2. 计算最短路径
                path = self.calculate_path(src_switch, dst_switch)
                print(" --- shortest --->===>[PATH] %s <---> %s: %s" % (src_ip, dst_ip, path))
                # 3. 下发流表
                self.install_flow(path, eth_type, src_ip, dst_ip, in_port, msg.buffer_id, msg.data)
        else:
            print(" --- shortest ---> src_dst_switches, 135", src_dst_switches)

    # 获得源交换机dpid和目标交换机的dpid
    def get_switches(self, dpid, in_port, src_ip, dst_ip):
        """ 根据src_ip求得dpid"""
        src_switch = dpid
        dst_switch = None

        src_location = self.discovery.get_host_ip_location(src_ip)  # (dpid, in_port)
        # FIXME: not_use_ports用成switch_all_ports_table一直BUG
        if in_port in self.discovery.not_use_ports[dpid]:  # {dpid: {port_no, ...}}
            print(f" --- shortest ---> src_location == (dpid, in_port): {src_location} == {(dpid, in_port)}", )
            if (dpid, in_port) == src_location:
                src_switch = src_location[0]
            else:
                return None

        dst_location = self.discovery.get_host_ip_location(dst_ip)
        if dst_location:
            dst_switch = dst_location[0]

        return src_switch, dst_switch

    def calculate_path(self, src_dpid, dst_dpid, weight_flag=False):
        """ 计算最短路径"""
        if weight_flag:
            self.discovery.calculate_shortest_paths(src_dpid, dst_dpid, self.discovery.calculate_weight)
        else:
           self.discovery.calculate_shortest_paths(src_dpid, dst_dpid)
        shortest_path = self.discovery.shortest_path_table[(src_dpid, dst_dpid)]
        # print(f" --- shortest --->  shortest_path_table  {self.discovery.shortest_path_table} " )
        # print(f" --- shortest --->  shortest_path  {shortest_path} " )
        return shortest_path

    def get_port(self, dst_ip):
        """ 根据目的ip获得出去的端口"""
        for key in self.discovery.access_table.keys():  # {(dpid, in_port): (src_ip, src_mac)}
            if dst_ip == self.discovery.access_table[key][0]:
                dst_port = key[1]
                return dst_port
        return None

    def get_port_pair(self, src_dpid, dst_dpid):
        """ 根据源dpid和目的dpid获得src.port_no, dst.port_no"""
        if (src_dpid, dst_dpid) in self.discovery.link_port_table:
            return self.discovery.link_port_table[(src_dpid, dst_dpid)]
        else:
            print(" --- shortest --->dpid: %s -> dpid: %s is not in links", (src_dpid, dst_dpid))
            return None

    def install_flow(self, path, eth_type, src_ip, dst_ip, in_port, buffer_id, data=None):
        """ 有多种情况需要考虑，即走哪个端口"""
        if path is None:
            print(" --- shortest --->Path Error")
            return
        else:
            first_dp = self.monitor.datapaths_table[path[0]]

            if len(path) > 2: # 多跳的情况(多于两个交换机连接)
                'host ------> in 1 out----->in 2 out----->in 3 out----->in 4 out ----->in 5 out -----> host'
                # print(" --- shortest --->len(path) > 2")
                for i in range(0, len(path)):  # 所有交换机安装流表
                    # 每一次给 i+1 的 datapath.id 的交换机安装流表
                    if i == 0:
                        # 第一台交换机的流表
                        out_port = self.get_port_pair(path[0], path[1])[0] # 第一对交换机 out 和 in ： 1 out----->in 2
                        self.send_flow_mod(first_dp, eth_type, src_ip, dst_ip, in_port, out_port)
                        self.send_flow_mod(first_dp, eth_type, dst_ip, src_ip, out_port, in_port)                        
                    elif i == len(path) - 1:
                        # 最后一台交换机的流表
                        port_pair = self.get_port_pair(path[-2], path[-1]) # 最后一对交换机的 out 和 in : 4 out ----->in 5
                        src_port = port_pair[1] # 最后一台交换机的 in : ----->in 5
                        dst_port = self.get_port(dst_ip) # # 最后一台交换机的 out : 5 out -----> host
                        last_dp = self.monitor.datapaths_table[path[-1]]
                        self.send_flow_mod(last_dp, eth_type, src_ip, dst_ip, src_port, dst_port)
                        self.send_flow_mod(last_dp, eth_type, dst_ip, src_ip, dst_port, src_port)  
                    else:
                        # 除了第一台和最后一台交换机
                        # 注释演示安装 2 交换机流表，需要知道 2 交换机两段的 in 端口和 out 端口 ：   in 2 out  
                        # 所以需要拿 2 连接 1 的端口和 2 连接 3 的端口               
                        port_pair = self.get_port_pair(path[i - 1], path[i]) # 前一对交换机 out 和 in : 1 out----->in 2
                        port_pair_next = self.get_port_pair(path[i], path[i + 1]) # 后一对对交换机 out 和 in  : 2 out----->in 3
                        # print(" --- shortest --->len(path) > 2 port_pair, port_pair_next", port_pair, port_pair_next)
                        if port_pair and port_pair_next:
                            src_port = port_pair[1]   # 第一对交换机的 in  : in 2
                            dst_port = port_pair_next[0] # 第二对交换机的 out  : 2 out
                            datapath = self.monitor.datapaths_table[path[i]]
                            # 下发正向流表
                            self.send_flow_mod(datapath, eth_type, src_ip, dst_ip, src_port, dst_port)
                            # 下发反向流表
                            self.send_flow_mod(datapath, eth_type, dst_ip, src_ip, dst_port, src_port)
                        else:
                            # print(f"shortestERROR--->len(path) > 2 "
                            #     f"path_0, path_1, port_pair: {path[i - 1], path[i], port_pair}, "
                            #     f"path_1, path_2, next_port_pair: {path[i], path[i + 1], port_pair_next}")
                            return

                
                # 所有交换机安装完流表后 packet_out 回第一台交换机
                self.send_packet_out(first_dp, buffer_id, in_port, out_port, data)

            elif len(path) == 2: # 两个交换机的线路
                print(" --- shortest --->len(path) == 2")
                port_pair = self.get_port_pair(path[-2], path[-1]) # 两个交换机连接的端口

                if port_pair is None:
                    print(" --- shortest --->port not found")
                    return

                src_port = port_pair[1] # 第二个交换机 in 的端口
                dst_port = self.get_port(dst_ip) # 第二个交换机 out 的端口

                if dst_port is None:
                    print(" --- shortest --->Last port is not found")
                    return

                last_dp = self.monitor.datapaths_table[path[-1]]  #最后一个交换机(dst所在的交换机)
                # TODO: 下发最后一个交换机的流表
                self.send_flow_mod(last_dp, eth_type, src_ip, dst_ip, src_port, dst_port)
                self.send_flow_mod(last_dp, eth_type, dst_ip, src_ip, dst_port, src_port)

                # port_pair = self.get_port_pair(path[0], path[1])
                # if port_pair is None:
                #     print(" --- shortest --->port not found in -2 switch")
                #     return

                out_port = port_pair[0] # 第一个交换机的 out 端口 
                # TODO: 发送倒数第二个交换机流表
                self.send_flow_mod(first_dp, eth_type, src_ip, dst_ip, in_port, out_port)
                self.send_flow_mod(first_dp, eth_type, dst_ip, src_ip, out_port, in_port)
                self.send_packet_out(first_dp, buffer_id, in_port, out_port, data)

            else: # src 和 dst 同一个交换机
                print(" --- shortest --->len(path) = 1")
                out_port = self.get_port(dst_ip)
                if out_port is None:
                    print(" --- shortest --->out_port is None in same dp")
                    return
                self.send_flow_mod(first_dp, eth_type, src_ip, dst_ip, in_port, out_port)
                self.send_flow_mod(first_dp, eth_type, dst_ip, src_ip, out_port, in_port)
                self.send_packet_out(first_dp, buffer_id, in_port, out_port, data)

    def send_flow_mod(self, datapath, eth_type, src_ip, dst_ip, src_port, dst_port):
        """ 下发流表"""
        parser = datapath.ofproto_parser
        actions = [parser.OFPActionOutput(dst_port)]

        match = parser.OFPMatch(in_port=src_port, eth_type=eth_type,
                                ipv4_src=src_ip, ipv4_dst=dst_ip)

        self.add_flow(datapath, 1, match, actions, idle_timeout=0, hard_timeout=0) # idle_timeout=15 hard_timeout=60

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst,
                                idle_timeout=idle_timeout, hard_timeout=hard_timeout)
        datapath.send_msg(mod)

    # 构造输出的包
    def _build_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        """ 构造输出的包"""
        actions = []
        if dst_port:
            actions.append(datapath.ofproto_parser.OFPActionOutput(dst_port))

        msg_data = None
        if buffer_id == datapath.ofproto.OFP_NO_BUFFER:
            if data is None:
                return None
            msg_data = data

        out = datapath.ofproto_parser.OFPPacketOut(datapath=datapath, buffer_id=buffer_id,
                                                   data=msg_data, in_port=src_port, actions=actions)

        return out

    def send_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        out = self._build_packet_out(datapath, buffer_id, src_port, dst_port, data)
        if out:
            datapath.send_msg(out)
