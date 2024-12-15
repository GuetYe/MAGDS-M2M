'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN_Practise/mininet/generate_topo.py
Date: 2023-06-07 10:33:51
Description: 
'''

import os
import sys
curr_path=os.path.dirname(os.path.abspath(__file__)) # =sys.path[0]也可以
parent_path=os.path.dirname(curr_path)
sys.path.append(parent_path)

os.chdir(sys.path[0])
# print("\n",os.getcwd())

import time


import xml.etree.ElementTree as ET
import networkx

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.node import UserSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.util import dumpNodeConnections



def parse_xml_topology(topology_path):
    """
    parse topology from topology.xml
    :return: topology graph, networkx.Graph()
             nodes_num,  int
             edges_num, int
    """
    tree = ET.parse(topology_path)
    root = tree.getroot()
    topo_element = root.find("topology")
    graph = networkx.Graph()
    for child in topo_element.iter():
        # parse nodes
        if child.tag == 'node':
            node_id = int(child.get('id'))
            graph.add_node(node_id)
        # parse link
        elif child.tag == 'link':
            from_node = int(child.find('from').get('node'))
            to_node = int(child.find('to').get('node'))
            graph.add_edge(from_node, to_node)

    nodes_num = len(graph.nodes)
    edges_num = len(graph.edges)

    print('nodes: ', nodes_num, '\n', graph.nodes, '\n',
          'edges: ', edges_num, '\n', graph.edges)
    return graph, nodes_num, edges_num


def generate_switch_port(graph):
    # 返回每个 node 的边字典
    switch_port_dict = {}
    for node in graph.nodes:
        switch_port_dict.setdefault(node, list(range(graph.degree[node])))
    return switch_port_dict


def get_mininet_device(net, idx: list, device='h'):
    """
        获得idx中mininet的实例, 如 h1, h2 ...;  s1, s2 ...
    :param net: mininet网络实例
    :param idx: 设备标号集合, list
    :param device: 设备名称 'h', 's'
    :return d: dict{idx: 设备mininet实例}
    """
    d = {}
    for i in idx:
        d.setdefault(i, net.get(f'{device}{i}'))

    return d


def net_h_ping_others(net,host_num):
    hosts = net.hosts
    for i,h in enumerate(hosts):
        if i+1==host_num:
            continue
        net.ping((hosts[host_num-1], h))


def run_ip_add_default(hosts: dict):
    """
        运行 ip route add default via 10.0.0.x 命令
    """
    _cmd = 'ip route add default via 10.0.0.'
    for i, h in hosts.items():
        print(_cmd + str(i))
        h.cmd(_cmd + str(i))
    print("---> run ip add default complete")


def _test_cmd(devices: dict, my_cmd):
    for i, d in devices.items():
        d.cmd(my_cmd)
        print(f'exec {my_cmd}zzz{i}')


class MyTopo(Topo):
    def __init__(self, graph):
        super(MyTopo, self).__init__()
        self.node_idx = graph.nodes
        self.edges_pairs = graph.edges
        self.switch2host={1:(1,2,3),5:(4,)}
        self.hosts_list=[]

        self.bw = 10  # Mbps  host -- switch  
        self.delay = 1  # ms

        # 添加交换机
        switches = {}
        for s in self.node_idx:
            switches.setdefault(s, self.addSwitch('s{0}'.format(s)))
            print('添加交换机:', s)

        print('交换机信息:', switches)
        # 添加交换机连接端口
        switch_port_dict = generate_switch_port(graph)
        
        # 添加链路
        links_info = {}
        for l in self.edges_pairs:
            port1 = switch_port_dict[l[0]].pop(0) + 1
            port2 = switch_port_dict[l[1]].pop(0) + 1
            self.addLink(switches[l[0]], switches[l[1]], port1=port1, port2=port2,bw=self.bw,delay=self.delay)
            links_info.setdefault(l, {"port1": port1, "port2": port2, "bw": self.bw , "delay": self.delay})

        # 添加主机
        switch_port_dict = generate_switch_port(graph)
        for s in self.switch2host: 
            for i,host in  enumerate(self.switch2host[s]):
                _h = self.addHost(f'h{host}', ip=f'10.0.0.{host}', mac=f'00.00.00.00.00.0{host}')
                self.hosts_list.append(host)
                self.addLink(_h, switches[s], port1=0, port2=switch_port_dict[s][-1]+1+1+i, bw=self.bw , delay=self.delay)

        # switches.setdefault(6, self.addSwitch('s6'))
        # _h = self.addHost(f'h5', ip=f'10.0.0.5', mac=f'00.00.00.00.00.05')
        # self.addLink(_h, switches[6], port1=0, port2=4, bw=self.bw , delay=self.delay)
        # self.addLink(switches[2], switches[6], port1=3, port2=1, bw=self.bw , delay=self.delay)
        # self.addLink(switches[3], switches[6], port1=3, port2=2, bw=self.bw , delay=self.delay)
        # self.addLink(switches[4], switches[6], port1=3, port2=3, bw=self.bw , delay=self.delay)
        # _h = self.addHost(f'h6', ip=f'10.0.0.6', mac=f'00.00.00.00.00.06')
        # self.addLink(_h, switches[2], port1=0, port2=4, bw=self.bw , delay=self.delay)

def main(graph, topo):
    net = Mininet(topo=topo, link=TCLink, controller=RemoteController, waitConnected=True, build=False)
    c0 = net.addController('c0', ip='127.0.0.1', port=6653)
    net.build()
    net.start()

    print("get hosts device list")
    hosts = get_mininet_device(net, topo.hosts_list, device='h')
    print("host信息 ：",hosts)
    print("===Dumping host connections")
    dumpNodeConnections(net.hosts)
    # print('===Wait ryu init')
    # time.sleep(10)
    # 添加网关ip
    # run_ip_add_default(hosts)



    CLI(net)
    net.stop()






if __name__=='__main__':
    xml_topology_path = r'./topologies/topo.xml'
    graph, nodes_num, edges_num = parse_xml_topology(xml_topology_path)
    topo = MyTopo(graph)
    main(graph, topo)