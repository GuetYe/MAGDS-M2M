'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN-WIFI - 副本/ryu/network_structure.py
Date: 2023-07-08 09:59:13
Description: 
            拓扑感知:
            1: get_switch ---> 获取 switch所有信息 ---> 记录下 datapath,dpid,port
            2: get_link ---> 获取 lldp 的链路信息 ---> 记录交换机相连的端口
            3: packet_in ---> 如果收到 arp 且未记录下该包的 mac 地址 ---> 记录下交换机端口所连的主机 mac 地址
            4: 上面 1 、2 、3记录的信息构建拓扑           

'''
import copy

from ryu.base import app_manager
from ryu.base.app_manager import lookup_service_brick
from ryu.ofproto import ofproto_v1_3
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls, MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.lib import hub
from ryu.lib.packet import packet, arp, ipv4, ethernet
from ryu.topology import event
from ryu.topology.api import get_switch, get_link

import networkx as nx
import matplotlib.pyplot as plt

import setting


class NetworkStructure(app_manager.RyuApp):
    """
    发现网络拓扑，保存网络结构
    """
    OFP_VERSION = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(NetworkStructure, self).__init__(*args, **kwargs)
        self.name = 'discovery'
        self.topology_api_app = self
        self.graph = nx.DiGraph()
        self.pre_graph = nx.DiGraph()
        self.access_table = {}  # {(映射dpid, in_port): (src_ip, src_mac)}
        self.switch_all_ports_table = {}  # {映射dpid: {port_no, ...}}       
        self.all_switches_dpid = self.switch_all_ports_table.keys() # dict_key[映射dpid]
        self.switch_port_table = {}  # {映射dpid: {port, ...}        
        self.link_port_table = {} # {(src.映射dpid, dst.映射dpid): (src.port_no, dst.port_no)}
        self.not_use_ports = {}  # {映射dpid: {port, ...}}  交换机之间没有用来连接的port
        self.shortest_path_table = {}  # {(src.映射dpid, dst.映射dpid): [path]}

        # 映射
        self.original_2_map_switch_id_dict = {}  # ap id dict
        self.original_switch_id_list = []  # ap id list

        # self._discover_thread = hub.spawn(self._discover_network_structure)

        self.first_flag = True

    def print_parameters(self):
        self.logger.info(
            " =========================== %s =========================== ", self.name)
        # self.logger.info(" --- discovery ---> graph: %s", self.graph.edges)
        # self.logger.info(" --- discovery ---> access_table: %s", self.access_table)
        # self.logger.info(
        #     " --- discovery ---> switch_all_ports_table: %s", self.switch_all_ports_table)
        # self.logger.info(
        #     " --- discovery ---> switch_port_table: %s", self.switch_port_table)
        # self.logger.info(
        #     " --- discovery ---> link_port_table: %s", self.link_port_table)
        # self.logger.info(
        #     " --- discovery ---> not_use_ports: %s", self.not_use_ports)
        # self.logger.info(" --- discovery ---> shortest_path_table: %s", self.shortest_path_table)
        # self.logger.info(
        #     " ================================================================= ")

        pass

    def _discover_network_structure(self):
        first_flag = True
        while True:
            hub.sleep(setting.DISCOVERY_PERIOD)
            self.get_topology(None)
            if self.pre_graph.edges != self.graph.edges or first_flag :
                self.print_parameters()
                first_flag = False

    def scheduler(self):
        self.get_topology(None)
        if setting.PRINT_SHOW or self.first_flag or (self.pre_graph.edges != self.graph.edges) :
            self.first_flag = False
            self.print_parameters()
            


    def add_flow(self, datapath, priority, match, actions):
        inst = [datapath.ofproto_parser.OFPInstructionActions(datapath.ofproto.OFPIT_APPLY_ACTIONS,
                                                              actions)]
        mod = datapath.ofproto_parser.OFPFlowMod(datapath=datapath, priority=priority,
                                                 match=match, instructions=inst)
        datapath.send_msg(mod)

    # Packet In
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # print(" --- discovery ---> discovery PacketIn")
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # 输入端口号
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        arp_pkt = pkt.get_protocol(arp.arp)

        if isinstance(arp_pkt, arp.arp):
            # self.logger.info(" --- discovery ---> arp packet")
            arp_src_ip = arp_pkt.src_ip
            src_mac = arp_pkt.src_mac
            # self.storage_access_info(datapath.id, in_port, arp_src_ip, src_mac)
            # ------------------------ dpid映射处理 -----------------------------------
            self.storage_access_info(self.original_2_map_switch_id_dict.get(
                datapath.id), in_port, arp_src_ip, src_mac)
            # -------------------------------------------------------------------------
    # 将packet-in解析的arp的网络通路信息存储

    def storage_access_info(self, dpid, in_port, src_ip, src_mac):
        if in_port in self.not_use_ports[dpid]:
            # print(" --- discovery --->", dpid, in_port, src_ip, src_mac)
            # print(" --- discovery ---> before-->", self.access_table)

            if (dpid, in_port) not in self.access_table.keys() or self.access_table[(dpid, in_port)] != (
                    src_ip, src_mac):
                self.access_table[(dpid, in_port)] = (
                    src_ip, src_mac)  # 只用dpid做键，port为值的画很多
                # print(
                #     " --- discovery --->  dpid  {}  discovery after-->".format(dpid), self.access_table)
            else:
                # print(" --- discovery ---> dpid  {}  inport  {}  network access already exist".format(
                #     dpid, in_port), end="\n", flush=False)
                pass
        else:
            # self.logger.info(" --- discovery --->in_port can't use",in_port)
            # print(
            #     " --- discovery --->  dpid  {}  in_port  {}  can't use".format(dpid, in_port))
            pass

    # 利用topology库获取拓扑信息
    # events = [event.EventSwitchEnter, event.EventSwitchLeave,
    #           event.EventPortAdd, event.EventPortDelete, event.EventPortModify,
    #           event.EventLinkAdd, event.EventLinkDelete]
    events = [ event.EventSwitchLeave]
    '''
    这里有个问题，就是时间时间太多的时候，节点规模一大，会一直有中断进入get_topology()导致线程卡死
    '''
    @set_ev_cls(events)
    def get_topology(self, ev):
        # self.logger.info(" --- discovery --->-----> EventSwitch/Port/Link")
        # 事件发生时，获得swicth列表
        switch_list = get_switch(self.topology_api_app)
        # print(' --- discovery ---> switch_list ', switch_list )
        # 将swicth添加到self.switch_all_ports_table
        for switch in switch_list:
            dpid = switch.dp.id

            # ------------------------ 未做dpid映射处理 -----------------------------------
            # self.switch_all_ports_table.setdefault(dpid, set())   # 有线
            # self.switch_port_table.setdefault(dpid, set())
            # self.not_use_ports.setdefault(dpid, set())
            # # 交换机添加端口
            # for p in switch.ports:
            #     self.switch_all_ports_table[dpid].add(p.port_no)
            # -------------------------------------------------------------------------

            # ------------------------ dpid映射处理 -----------------------------------
            # 无线用映射后的id做键值
            self.switch_all_ports_table.setdefault(
                self.original_2_map_switch_id_dict.get(dpid), set())
            self.switch_port_table.setdefault(
                self.original_2_map_switch_id_dict.get(dpid), set())
            self.not_use_ports.setdefault(
                self.original_2_map_switch_id_dict.get(dpid), set())
            for p in switch.ports:
                self.switch_all_ports_table[self.original_2_map_switch_id_dict.get(
                    dpid)].add(p.port_no)
            # -------------------------------------------------------------------------

        # 更新交换机表
        self.all_switches_dpid = self.switch_all_ports_table.keys()

        # 获得link
        link_list = get_link(self.topology_api_app)
        # print(' --- discovery --->  link_list   ',link_list)
        self.link_port_table = {}
        # 将link添加到self.link_table
        for link in link_list:
            src = link.src  # 实际是个port实例，我找了半天
            dst = link.dst

            # ------------------------ 未做dpid映射处理 -----------------------------------
            # self.link_port_table[(src.dpid, dst.dpid)] = (src.port_no, dst.port_no)
            # if src.dpid in self.all_switches_dpid:
            #     self.switch_port_table[src.dpid].add(src.port_no)
            # if dst.dpid in self.all_switches_dpid:
            #     self.switch_port_table[dst.dpid].add(dst.port_no)
            # -------------------------------------------------------------------------

    

    def calculate_weight(self, node1, node2, weight_dict):
        """ 计算路径时，weight可以调用函数，该函数根据因子计算 bw * factor - delay * (1 - factor) 后的weight"""
        # weight可以调用的函数
        assert 'bw' in weight_dict and 'delay' in weight_dict, "edge weight should have bw and delay"
        try:
            weight = weight_dict['bw'] * setting.FACTOR - \
                weight_dict['delay'] * (1 - setting.FACTOR)
            return weight
        except TypeError:
            print("discovery ERROR---> weight_dict['bw']: ", weight_dict['bw'])
            print(
                "discovery ERROR---> weight_dict['delay']: ", weight_dict['delay'])
            return None

    def calculate_shortest_paths(self, src_dpid, dst_dpid, weight=None):
        """ 计算src到dst的最短路径，存在self.shortest_path_table中"""
        # TODO: 应该深拷贝，防止没算出来时改变graph
        # try:
        self.shortest_path_table[(src_dpid, dst_dpid)] = nx.shortest_path(self.graph, src_dpid, dst_dpid,
                                                                          weight=weight, method=setting.METHOD)

    def calculate_all_nodes_shortest_paths(self, weight=None):
        """ 根据已构建的图，计算所有nodes间的最短路径，weight为权值，可以为calculate_weight()该函数"""
        self.shortest_path_table = {}  # 先清空，再计算
        for src in self.graph.nodes():
            for dst in self.graph.nodes():
                if src != dst:
                    self.calculate_shortest_paths(src, dst, weight=weight)
                else:
                    continue

    def get_host_ip_location(self, host_ip):
        """
            通过host_ip查询 self.access_table: {(dpid, in_port): (src_ip, src_mac)}
            获得(dpid, in_port)
        """
        for key in self.access_table.keys():  # {(dpid, in_port): (src_ip, src_mac)}
            if self.access_table[key][0] == host_ip:
                # print(" --- discovery --->zzzz---> key", key)
                return key
        # FIXME: 刚开始这里写成else了，导致一直循环
        # print(" --- discovery --->%s location is not found" % host_ip)
        return None

    def show_graph_plt(self):
        FIRST = True
        if self.pre_graph != self.graph or FIRST:
            FIRST = False
            nx.draw_networkx(self.graph, with_labels=True)
            plt.show()
