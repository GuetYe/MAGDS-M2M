'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN-WIFI/ryu/network_monitor.py
Date: 2023-07-08 09:59:13
Description: 
            1. 发送端口描述请求 ---> 收到 reply ---> dpid_port_features_table {dpid:{port_no: (config, state, curr_speed, max_speed)}}
            2. 发送端口统计请求 ---> 收到 reply ---> port_stats_table {(dpid, port_no): [(stat.tx_bytes, stat.rx_bytes, stat.rx_errors,stat.duration_sec, stat.duration_nsec), .....]}
            3. 有了 1 、2 两表格的信息，可以得到端口固定时间内的数据，speed= (前一个时间数据量+后一个时间数据量)/(两个时间和)
            4. 带宽 = max_speed - curr_speed
            5. 带宽信息丢进拓扑的bw中

'''

from operator import attrgetter

from ryu.base import app_manager
from ryu.ofproto import ofproto_v1_3
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.lib import hub
from ryu.base.app_manager import lookup_service_brick

import setting


class NetworkMonitor(app_manager.RyuApp):
    """ 监控网络流量状态"""
    # TODO: 这个忘了，默认是1.5，ofp的数据结构就变了，找了半天bug
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(NetworkMonitor, self).__init__(*args, **kwargs)
        self.name = 'monitor'
        self.datapaths_table = {}  # {映射dpid: datapath}
        self.dpid_port_features_table = {}  # {映射dpid:{port_no: (config, state, curr_speed, max_speed)}}
        self.port_stats_table = {}  # {(映射dpid, port_no): [(stat.tx_bytes, stat.rx_bytes, stat.rx_errors,stat.duration_sec, stat.duration_nsec), .....]}
        self.flow_stats_table = {}  # {映射dpid:{(in_port, ipv4_dsts, out_port): (packet_count, byte_count, duration_sec, duration_nsec)}}
        self.port_speed_table = {}  # {(映射dpid, port_no): [speed, .....]}
        self.flow_speed_table = {}  # {映射dpid: {(in_port, ipv4_dsts, out_port): speed}}
        self.port_flow_dpid_stats = {'port': {}, 'flow': {}} # {'port': {映射dpid : body}, 'flow': {映射dpid : body}}
        self.port_free_bandwidth = {}  # {映射dpid: {port_no: curr_bw}}

        self.port_loss = {}  # 端口的丢包率
        self.port_pkt_err = {} # 端口错包率
        self.port_pkt_drop = {}  # 端口弃包个数

        self.network_structure = lookup_service_brick("discovery")  # 创建一个NetworkStructure的实例

        # self.monitor_thread = hub.spawn(self._monitor)

    def print_parameters(self):
        self.logger.info(" =========================== %s =========================== ", self.name)
        # print(" --- monitor ---> self.datapaths_table", self.datapaths_table)
        # print(" --- monitor ---> self.dpid_port_features_table", self.dpid_port_features_table)
        # print(" --- monitor ---> self.port_stats_table", self.port_stats_table)
        # print(" --- monitor ---> self.flow_stats_table", self.flow_stats_table)
        # print(" --- monitor ---> self.port_speed_table", self.port_speed_table)
        # print(" --- monitor ---> self.flow_speed_table", self.flow_speed_table)
        # print(" --- monitor ---> self.port_loss", self.port_loss)
        # print(" --- monitor ---> self.port_free_bandwidth", self.port_free_bandwidth)
        # self.logger.info(" ================================================================= ")

    def print_parameters_(self):
        print("monitor---------- %s ----------", self.name)
        for attr, value in self.__dict__.items():
            print(" --- monitor ---> %s: %s" % attr, value)
        print("monitor===================================")

    def _monitor(self):
        while True:
            hub.sleep(setting.MONITOR_PERIOD)
            self._request_stats()
            self.print_parameters()
            self.create_bandwidth_graph()
            self.create_loss_graph()

    def scheduler(self):
        self._request_stats()
        self.create_bandwidth_graph()
        self.create_loss_graph()
        if setting.PRINT_SHOW :
            self.print_parameters()

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        """ 存放所有的datapath实例"""
        datapath = ev.datapath  # OFPStateChange类可以直接获得datapath
        # ------------------------ dpid映射处理 -----------------------------------
        dpid =  self.network_structure.original_2_map_switch_id_dict.get(datapath.id)
        if ev.state == MAIN_DISPATCHER:
            if dpid not in self.datapaths_table:
                # self.logger.info(" --- monitor ---> register datapath: %016x", datapath.id) # 016x : 0:补足位数 16:16位输出 x：16进制
                print(" --- monitor ---> register datapath :", dpid) # 016x : 0:补足位数 16:16位输出 x：16进制
                # self.datapaths_table[datapath.id] = datapath
                self.datapaths_table[dpid] = datapath

                # 一些初始化
                self.dpid_port_features_table.setdefault(dpid, {})
                self.flow_stats_table.setdefault(dpid, {})

        elif ev.state == DEAD_DISPATCHER:
            if dpid in self.datapaths_table:
                self.logger.info(" --- monitor ---> unreigster datapath: %016x", datapath.id)
                del self.datapaths_table[dpid]
        # -------------------------------------------------------------------------

    # 主动发送request，请求状态信息
    def _request_stats(self):
        # print(" --- monitor ---> send request --->   ---> send request ---> ")
        for datapath in self.datapaths_table.values():
            # self.logger.info(" --- monitor ---> send stats request: %016x", datapath.id)
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser

            # 1. 端口描述请求
            req = parser.OFPPortDescStatsRequest(datapath, 0)  #
            datapath.send_msg(req)

            # 2. 端口统计请求
            req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)  # 所有端口
            datapath.send_msg(req)

            # 3. 单个流统计请求
            # req = parser.OFPFlowStatsRequest(datapath)
            # datapath.send_msg(req)


    # 处理上面请求的回复 OFPFlowStatsRequest
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        """ 存储flow的状态，算这个干啥。。"""
        msg = ev.msg
        body = msg.body
        datapath = msg.datapath
        
        # ------------------------ dpid映射处理 -----------------------------------
        # dpid = dpid = datapath.id
        dpid = self.network_structure.original_2_map_switch_id_dict.get(ev.msg.datapath.id)
        # -------------------------------------------------------------------------

        self.port_flow_dpid_stats['flow'][dpid] = body
        # print(" --- monitor ---> body", body)

        for stat in sorted([flowstats for flowstats in body if flowstats.priority == 1],
                           key=lambda flowstats: (flowstats.match.get('in_port'), flowstats.match.get('ipv4_dst'))):
            # print(" --- monitor ---> stat.match", stat.match)
            # print(" --- monitor ---> stat", stat)
            key = (stat.match['in_port'], stat.match['ipv4_dst'],
                   stat.instructions[0].actions[0].port)
            value = (stat.packet_count, stat.byte_count, stat.duration_sec, stat.duration_nsec)
            self._save_stats(self.flow_stats_table[dpid], key, value, 5)

            pre_bytes = 0
            delta_time = setting.MONITOR_PERIOD
            value = self.flow_stats_table[dpid][key]
            if len(value) > 1:
                pre_bytes = value[-2][1]
                delta_time = self._calculate_delta_time(value[-1][2], value[-1][3],
                                                        value[-2][2], value[-2][3])
            speed = self._calculate_speed(self.flow_stats_table[dpid][key][-1][1], pre_bytes, delta_time)
            self.flow_speed_table.setdefault(dpid, {})
            self._save_stats(self.flow_speed_table[dpid], key, speed, 5)

    # 存多次数据，比如一个端口存上一次的统计信息和这一次的统计信息
    @staticmethod
    def _save_stats(_dict, key, value, keep):
        if key not in _dict:
            _dict[key] = []
        _dict[key].append(value)

        if len(_dict[key]) > keep:
            _dict[key].pop(0)  # 弹出最早的数据

    def _calculate_delta_time(self, now_sec, now_nsec, pre_sec, pre_nsec):
        """ 计算统计时间, 即两个消息时间差"""
        return abs(self._calculate_seconds(pre_sec, pre_nsec) - self._calculate_seconds(now_sec, now_nsec))

    @staticmethod
    def _calculate_seconds(sec, nsec):
        """ 计算 sec + nsec 的和，单位为 seconds"""
        return sec + nsec / (10 ** 9)

    @staticmethod
    def _calculate_speed(now_bytes, pre_bytes, delta_time):
        """ 计算统计流量速度"""
        if delta_time:
            return abs((now_bytes - pre_bytes) / delta_time)
        else:
            return 0

    def _calculate_port_free_bandwidth(self, dpid, port_no, speed):
        port_features = self.dpid_port_features_table.get(dpid).get(port_no)
        if port_features:
            capacity = port_features[2]  # curr_speed
            # 当前带宽
            curr_bw = max(capacity / 10 ** 6 - speed * 8 / 10 ** 6, 0)  # Mbit/s
            self.port_free_bandwidth.setdefault(dpid, {})
            self.port_free_bandwidth[dpid][port_no] = curr_bw
        else:
            self.logger.info(" --- monitor --->Fail in getting port features")

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status_handler(self, ev):
        """ 处理端口状态： ADD, DELETE, MODIFIED"""
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto

        if msg.reason == ofp.OFPPR_ADD:
            reason = 'ADD'
        elif msg.reason == ofp.OFPPR_DELETE:
            reason = 'DELETE'
        elif msg.reason == ofp.OFPPR_MODIFY:
            reason = 'MODIFY'
        else:
            reason = 'unknown'

        self.logger.info('---> OFPPortStatus received: reason=%s desc=%s',
                         reason, msg.desc)

    # 通过获得的网络拓扑，更新其bw权重
    def create_bandwidth_graph(self):
        # link_port_table = self.network_structure.link_port_table
        # print(" --- monitor ---> create bandwidth graph")
        for link in self.network_structure.link_port_table: # link_port_table -> {(src.映射dpid, dst.映射dpid): (src.port_no, dst.port_no)}
            src_dpid, dst_dpid = link
            src_port, dst_port = self.network_structure.link_port_table[link]
            # FIXME: dst_dpid 打成了 dst_port
            if src_dpid in self.port_free_bandwidth.keys() and dst_dpid in self.port_free_bandwidth.keys():
                src_port_bw = self.port_free_bandwidth[src_dpid][src_port]
                # print(" --- monitor ---> src_port_bw", src_port_bw)
                dst_port_bw = self.port_free_bandwidth[dst_dpid][dst_port]
                # print(" --- monitor ---> dst_port_bw", dst_port_bw)
                if src_port_bw and dst_port_bw:
                    src_dst_bandwitdh = min(src_port_bw, dst_port_bw)  # 是这样吗
                else:
                    src_dst_bandwitdh = 1
                    # src_dst_bandwitdh = 10
                # print(" --- monitor ---> src_dst_bandwitdh", src_dst_bandwitdh)
                # 对图的edge设置bw值
                self.network_structure.graph[src_dpid][dst_dpid]['bw'] = src_dst_bandwitdh
            else:
                # print(" --- monitor ---> not in port_free_bandwidth", src_dpid, dst_dpid)
                self.network_structure.graph[src_dpid][dst_dpid]['bw'] = 1

        # print(" --- monitor ---> ", self.network_structure.graph.edges(data=True))
        # print(" --- monitor --->" * 2, self.network_structure.count + 1)

    # calculate loss tx - rx / tx
    def calculate_loss_of_link(self):
        """
            发端口 和 收端口 ,端口loss
        """
        for link, port in self.network_structure.link_port_table.items():
            src_dpid, dst_dpid = link
            src_port, dst_port = port
            if (src_dpid, src_port) in self.port_stats_table.keys() and (dst_dpid, dst_port) in self.port_stats_table.keys():
                # {(dpid, port_no): (stat.tx_bytes, stat.rx_bytes, stat.rx_errors, stat.duration_sec,
                # stat.duration_nsec, stat.tx_packets, stat.rx_packets)}
                # 1. 顺向  2022/3/11 packets modify--> bytes
                #计算loss，丢包率
                tx = self.port_stats_table[(src_dpid, src_port)][-1][0]  # tx_bytes
                rx = self.port_stats_table[(dst_dpid, dst_port)][-1][1]  # rx_bytes
                loss_ratio = abs(float(tx - rx) / tx) * 100
                self._save_stats(self.port_loss, link, loss_ratio, 5)
                # print(f" --- monitor ---> [{link}]({dst_dpid}, {dst_port}) rx: ", rx, "tx: ", tx,
                #       "loss_ratio: ", loss_ratio)

                # 计算错包率
                rx_err = self.port_stats_table[(src_dpid, src_port)][-1][2] # rx_err_bytes 
                rx = self.port_stats_table[(dst_dpid, dst_port)][-1][1]  # rx_bytes
                pkt_err = (rx_err/rx) * 100
                self._save_stats(self.port_pkt_err, link, pkt_err, 5)

                # 计算弃包个数
                tx_packets = self.port_stats_table[(src_dpid, src_port)][-1][-2] # tx_packets
                rx_packets = self.port_stats_table[(dst_dpid, dst_port)][-1][-1]  # rx_packets
                pkt_drop = abs(tx_packets - rx_packets)
                self._save_stats(self.port_pkt_drop, link, pkt_drop, 5)



                # 2. 逆项
                tx = self.port_stats_table[(dst_dpid, dst_port)][-1][0]  # tx_bytes
                rx = self.port_stats_table[(src_dpid, src_port)][-1][1]  # rx_bytes
                loss_ratio = abs(float(tx - rx) / tx) * 100
                self._save_stats(self.port_loss, link[::-1], loss_ratio, 5)

                # print(f" --- monitor ---> [{link[::-1]}]({dst_dpid}, {dst_port}) rx: ", rx, "tx: ", tx,
                #       "loss_ratio: ", loss_ratio)

                # 计算错包率
                rx_err = self.port_stats_table[(dst_dpid, dst_port)][-1][2] # rx_err_bytes 
                rx = self.port_stats_table[(src_dpid, src_port)][-1][1]  # rx_bytes
                pkt_err = (rx_err/rx) * 100
                self._save_stats(self.port_pkt_err, link, pkt_err, 5)

                # 计算弃包个数
                tx_packets = self.port_stats_table[(dst_dpid, dst_port)][-1][-2] # tx_packets
                rx_packets = self.port_stats_table[(src_dpid, src_port)][-1][-1]  # rx_packets
                pkt_drop = abs(tx_packets - rx_packets)
                self._save_stats(self.port_pkt_drop, link, pkt_drop, 5)


            else:
                # self.logger.info(" --- monitor --->   calculate_loss_of_link error", )
                pass

    # create loss graph 
    def create_loss_graph(self):
        """从1 往2 和 从2 往1,取最大作为链路loss """
        for link in self.network_structure.link_port_table:
            src_dpid = link[0]
            dst_dpid = link[1]
            if link in self.port_loss.keys() and link[::-1] in self.port_loss.keys():
                src_loss = self.port_loss[link][-1]  # 1-->2  -1取最新的那个
                dst_loss = self.port_loss[link[::-1]][-1]  # 2-->1
                link_loss = max(src_loss, dst_loss)  # 百分比 max loss between port1 and port2
                self.network_structure.graph[src_dpid][dst_dpid]['loss'] = link_loss

                # print(f" --- monitor --->  create_loss_graph link[{link}]_loss: ", link_loss)
            else:
                self.network_structure.graph[src_dpid][dst_dpid]['loss'] = 100
            
            if link in self.port_pkt_err.keys() and link[::-1] in self.port_pkt_err.keys():
                src_pkt_err = self.port_pkt_err[link][-1]  # 1-->2  -1取最新的那个
                dst_pkt_err = self.port_pkt_err[link[::-1]][-1]  # 2-->1
                link_pkt_err = max(src_pkt_err , dst_pkt_err )  # 百分比 max loss between port1 and port2
                self.network_structure.graph[src_dpid][dst_dpid]['pkt_err'] = link_pkt_err

                # print(f" --- monitor --->  create_loss_graph link[{link}]_loss: ", link_loss)
            else:
                self.network_structure.graph[src_dpid][dst_dpid]['pkt_err'] = -1
            
            if link in self.port_pkt_drop.keys() and link[::-1] in self.port_pkt_drop.keys():
                src_pkt_drop = self.port_pkt_drop[link][-1]  # 1-->2  -1取最新的那个
                dst_pkt_drop = self.port_pkt_drop[link[::-1]][-1]  # 2-->1
                link_pkt_drop = max(src_pkt_drop, dst_pkt_drop)  # 百分比 max loss between port1 and port2
                self.network_structure.graph[src_dpid][dst_dpid]['pkt_drop'] = link_pkt_drop

                # print(f" --- monitor --->  create_loss_graph link[{link}]_loss: ", link_loss)
            else:
                self.network_structure.graph[src_dpid][dst_dpid]['pkt_drop'] = -1
