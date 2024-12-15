'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN-WIFI/mininet-wifi/generate_topo_wifi_copy_2.py
Date: 2023-07-24 15:23:58
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

from mn_wifi.topo import Topo
from mn_wifi.net import Mininet_wifi
from mininet.node import RemoteController
from mn_wifi.link import wmediumd
from mininet.node import UserSwitch
from mininet.link import TCLink
from mn_wifi.cli import CLI
from mininet.log import setLogLevel , info
from mininet.util import dumpNodeConnections


# √
def parse_wifi_xml_topology(topology_path):
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
    ap_location_list = []
    sta_location_list = []
    for child in topo_element.iter():
        # parse nodes
        if child.tag == 'node':
            node_id = int(child.get('id'))
            graph.add_node(node_id)
            # 解析AP和STA的坐标
            ap_location = str(child.find('locationap').get('coordinate'))
            sta_location = str(child.find('locationsta').get('coordinate'))
            # 添加进列表
            ap_location_list.append(ap_location)  
            sta_location_list.append(sta_location)
        # parse link
        elif child.tag == 'link':
            from_node = int(child.find('from').get('node'))
            to_node = int(child.find('to').get('node'))
            graph.add_edge(from_node, to_node)

    nodes_num = len(graph.nodes)
    edges_num = len(graph.edges)

    print('nodes: ', nodes_num, '\n', graph.nodes, '\n',
          'edges: ', edges_num, '\n', graph.edges , '\n'
          'ap_location_list  : \n' , ap_location_list , '\n' ,
          'sta_location  : \n',sta_location_list)
    return graph, nodes_num, edges_num , ap_location_list , sta_location_list

# √
def generate_ap_port(graph):
    # 返回每个 node 的边字典
    ap_port_dict = {}
    for node in graph.nodes:
        ap_port_dict.setdefault(node, list(range(graph.degree[node])))
    return ap_port_dict

def generate_node_idx(graph):
    node_idx = {}
    for idx , node in enumerate(graph.nodes):
        node_idx[node]= idx+1
    return node_idx


def get_node_location(gragh):
    location = []
    for node in gragh.nodes:
        location.append((gragh.nodes.get(node)['Longitude'] * 100, gragh.nodes.get(node)['Latitude'] * 100, 0))
    return location

# √
def get_mininet_device(net, idx: list, device='sta'):
    """
    获得idx中mininet-wifi的实例, 如 sta1, sta2 ...;  ap1, ap2 ...
    :param net: mininet网络实例
    :param idx: 设备标号集合, list
    :param device: 设备名称 'h', 's'
    :return d: dict{idx: 设备mininet实例}
    """
    d = {}
    for i in idx:
        d.setdefault(i, net.get(f'{device}{i}'))

    return d


def net_sta_ping_others(net,sta_num):
    stations = net.stations
    for i,h in enumerate(stations):
        if i+1==sta_num:
            continue
        net.ping((stations[sta_num-1], h))


def cal_ap_distance(ap1_location, ap2_location):
    ap1_x, ap1_y, ap1_z = ap1_location.split(',')
    ap2_x, ap2_y, ap2_z = ap2_location.split(',')

    x = abs(int(ap1_x) - int(ap2_x))
    y = abs(int(ap1_y) - int(ap2_y))

    distance = pow(x**2+y**2, 0.5)

    return distance


def run_ip_add_default(hosts: dict):
    """
        运行 ip route add default via 192.168.0.x 命令
    """
    _cmd = 'ip route add default via 192.168.0.'
    for i, h in hosts.items():
        print(_cmd + str(i))
        h.cmd(_cmd + str(i))
    print("---> run ip add default complete")


def _test_cmd(devices: dict, my_cmd):
    for i, d in devices.items():
        d.cmd(my_cmd)
        print(f'exec {my_cmd}zzz{i}')


class My14Topo():
    def __init__(self, graph ):
        super(My14Topo, self).__init__()
        "Create a network."
        self.net = Mininet_wifi(controller=RemoteController)

        self.graph = graph
        self.node_idx = generate_node_idx(graph)
        self.edges_pairs = graph.edges

        self.hosts_list=[]

        self.bw = 10  # Gbps还是Mbps?  host -- switch  
        self.delay = 1  # ms

        self.host_port = 9
        self.snooper_port = 10
        self.ap_position = get_node_location(graph)  #['100,100,0', '50,50,0', '150,50,0']
        self.sta_position = get_node_location(graph)  #['100,110,0', '40,50,0', '160,50,0']

    def topology(self, args):
        print(" ------------------ Creating nodes ------------------ ")
        aps = {}
        stas = {}
        for idx in self.node_idx.values():
            if idx < 10:
                # 添加AP
                ap = self.net.addAccessPoint(f'ap{idx}',ssid=f"ap{idx}-ssid",
                                            mode="g", channel="5",position=str(self.ap_position[idx-1])[1:-1], mac="{}0:00:00:00:00:00".format(idx))
                aps.setdefault(idx , ap)
                print('添加AP:', idx)

                # 添加sta
                sta = self.net.addStation(f'sta{idx}',
                                        mac=f'00:00:00:00:00:0{idx}', ip=f'192.168.0.{idx}/24', position=self.sta_position[idx-1])
                stas.setdefault(idx , sta)
                print(self.sta_position[idx-1])
                print('添加STA:', idx) 
            else:
                # 添加AP
                ap = self.net.addAccessPoint(f'ap{idx}',ssid=f"ap{idx}-ssid",
                                              mode="g", channel="5",position=str(self.ap_position[idx-1])[1:-1], mac="00:{}:00:00:00:00".format(idx))
                aps.setdefault(idx , ap)
                print('添加AP:', idx)

                # 添加sta
                sta = self.net.addStation(f'sta{idx}',
                                        mac=f'00:00:00:00:00:{idx}', ip=f'192.168.0.{idx}/24', position=self.sta_position[idx-1])
                stas.setdefault(idx , sta)
                print(self.sta_position[idx-1])
                print('添加STA:', idx)   

        # 添加控制器  
        c0 = self.net.addController('c0', controller=RemoteController)

        print(" ------------------ Configuring Propagation Model ------------------ ")
        self.net.setPropagationModel(model="logDistance", exp=4.5)

        print(" ------------------ Configuring nodes ------------------ ")
        self.net.configureNodes()

        # ap 之间添加 link 
        print(" ------------------ Adding Links ------------------ ")
        ap_port_dict = generate_ap_port(self.graph)
        links_info = {}
        for l in self.edges_pairs:
            port1 = ap_port_dict[l[0]].pop(0) + 1
            port2 = ap_port_dict[l[1]].pop(0) + 1
            self.net.addLink(aps[self.node_idx[l[0]]], aps[self.node_idx[l[1]]], cls=wmediumd , bw=self.bw, delay=self.delay)
            print('\n')
        print('\n')

        # AP<--->STA
        for i in self.node_idx.values():
            self.net.addLink(stas[i], aps[i], bw=self.bw , delay=self.delay )

            
        for i in aps.keys():
            time.sleep(0.3)
            aps[i].start([c0])

        # 画topo
        self.net.plotGraph(max_x=1600, max_y=4700)

        print(" ------------------ Starting network ------------------ ")
        self.net.build()
        c0.start()

        print(" ------------------ get stations device list ------------------ ")
        stations = get_mininet_device(self.net, self.node_idx.values(), device='sta')
        print(" ------------------ Dumping host connections ------------------ ")
        dumpNodeConnections(self.net.stations)

        print( ' ------------------ add gatway ------------------ ')
        run_ip_add_default(stations)


        print(" ------------------ Running CLI ------------------ ")
        CLI(self.net)

        print(" ------------------ Stopping network ------------------ ")
        self.net.stop()



if __name__=='__main__':
    xml_topology_path = r'topology-zoo/Arnes.gml'   
    G = networkx.read_gml(xml_topology_path)
    mytopo = My14Topo(G)
    setLogLevel('info')
    mytopo.topology(sys.argv)    