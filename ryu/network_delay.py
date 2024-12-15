'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN-WIFI - 副本/ryu/network_delay.py
Date: 2023-07-08 09:59:13
Description: 
            发送时延:发送时延是主机或者路由器发送数据帧所需要的时延; 发送时延=数据帧长度/发送的速率
            传播时延:传播时延是电磁波在信道中传播一定的距离花费的时间; 传播时延=传输媒介长度/电磁波在信道上的传播速率
            处理时延:主机或者路由器处理数据花费的时间; 
            排队时延:数据在进入路由器后排队等待的时间;
            
            测量链路时延
                                ┌------Ryu------┐
                                |               |
                src echo latency|               |dst echo latency
                                |               |
                            SwitchA------------SwitchB
                                --->fwd_delay--->
                                <---reply_delay<---


            1. ryu echo携带时间戳 ---> 交换机回复 ---> src echo latency = 收到的时间戳 - echo时间戳
            2. dst echo latency同理
            3. 11dp : RYU->A->B->RYU
                      RYU->B->A->RYU
            4. fwd_delay = (lldp - src echo latency - dst echo latency)/2

'''
import time

from ryu.base import app_manager
from ryu.base.app_manager import lookup_service_brick
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.topology.switches import Switches, LLDPPacket

import setting
import network_structure
import network_monitor


class NetworkDelayDetector(app_manager.RyuApp):
    """ 测量链路的时延"""
    OFP_VERSION = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'switches': Switches}

    def __init__(self, *args, **kwargs):
        super(NetworkDelayDetector, self).__init__(*args, **kwargs)
        self.name = 'detector'

        self.network_structure = lookup_service_brick('discovery')
        self.network_monitor = lookup_service_brick('monitor')
        self.switch_module = lookup_service_brick('switches')

        self.switch_module = kwargs['switches']
        # self.network_structure = kwargs['discovery']
        # self.network_monitor = kwargs['monitor']

        self.echo_delay_table = {}  # {映射dpid: ryu_ofps_delay}
        self.lldp_delay_table = {}  # {src_映射dpid: {dst_映射dpid: delay}}
        self.echo_interval = 0.05

        # self.datapaths_table = self.network_monitor.datapaths_table

        # self._detector_thread = hub.spawn(self._detector)

    def _detector(self):
        while True:
            hub.sleep(setting.DELAY_PERIOD)
            self._send_echo_request()
            self.create_delay_graph()
            self.print_delay_stats()

    def scheduler(self):
        self._send_echo_request()
        self.create_delay_graph()
        if setting.PRINT_SHOW :
            self.print_delay_stats()

    # 利用echo发送时间，与接收时间相减
    # 1. 发送echo request
    def _send_echo_request(self):
        """ 发送echo请求"""
        
        for datapath in self.network_monitor.datapaths_table.values():
            # print('发送echo请求')
            parser = datapath.ofproto_parser
            data = time.time()
            echo_req = parser.OFPEchoRequest(datapath, b"%.12f" % data)
            datapath.send_msg(echo_req)
            hub.sleep(self.echo_interval)  # 防止发太快，那边收不到


    # 利用LLDP时延
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """ 解析LLDP包, 这个处理程序可以接收所有可以接收的数据包, swicthes.py l:769"""
        # print("--- detector ---> PacketIn")
        try:
            recv_timestamp = time.time()
            msg = ev.msg
            # ------------------------ dpid映射处理 -----------------------------------
            # dpid = msg.datapath.id
            dpid = self.network_structure.original_2_map_switch_id_dict.get(ev.msg.datapath.id)
            # -------------------------------------------------------------------------

            src_dpid, src_port_no = LLDPPacket.lldp_parse(msg.data)                      
            # print("---> self.switch_module.ports", self.switch_module.ports)

            for port in self.switch_module.ports.keys():
                if src_dpid == port.dpid and src_port_no == port.port_no:
                    send_timestamp = self.switch_module.ports[port].timestamp
                    if send_timestamp:
                        delay = recv_timestamp - send_timestamp
                        # print("--- detector ---> PacketIn  lldp_delay src {}    dst {} :    delay {} ".format(src_dpid,dpid,delay))
                    else:
                        delay = 0

                    # ------------------------ dpid映射处理 -----------------------------------
                    src_dpid = self.network_structure.original_2_map_switch_id_dict.get(src_dpid)
                    # -------------------------------------------------------------------------

                    self.lldp_delay_table.setdefault(src_dpid, {})
                    self.lldp_delay_table[src_dpid][dpid] = delay  # 存起来
        except LLDPPacket.LLDPUnknownFormat as e:
            return

    def create_delay_graph(self):
        # 遍历所有的边
        # print('---> create delay graph')
        for src, dst in self.network_structure.graph.edges:
            delay = self.calculate_delay(src, dst)
            self.network_structure.graph[src][dst]['delay'] = delay
        # print("---> ", self.network_structure.graph.edges(data=True))
        # print("--->" * 2, self.network_structure.count + 1)

    def calculate_delay(self, src, dst):
        """
                        ┌------Ryu------┐
                        |               |
        src echo latency|               |dst echo latency
                        |               |
                    SwitchA------------SwitchB
                         --->fwd_delay--->
                         <---reply_delay<---
        """

        # print("*************  self.lldp_delay_table",self.lldp_delay_table,
        #       '\n*************  self.echo_delay_table'  ,self.echo_delay_table,
        #       '\n##############',src,'   ',dst)
        fwd_delay = self.lldp_delay_table[src][dst]
        reply_delay = self.lldp_delay_table[dst][src]
        ryu_ofps_src_delay = self.echo_delay_table[src]
        ryu_ofps_dst_delay = self.echo_delay_table[dst]

        delay = (fwd_delay + reply_delay - ryu_ofps_src_delay - ryu_ofps_dst_delay) / 2
        return max(delay, 0)

    def print_delay_stats(self):
        self.logger.info(" =========================== %s =========================== ", self.name)
        # self.logger.info(" ---------------------------------- ")
        # self.logger.info(" src    dst :    delay ")
        # for src in self.lldp_delay_table.keys():
        #     for dst in self.lldp_delay_table[src].keys():
        #         delay = self.lldp_delay_table[src][dst]
        #         self.logger.info(" %s <---> %s : %s", src, dst, delay)
        # self.logger.info(" ---------------------------------- ")