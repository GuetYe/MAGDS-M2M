'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN-WIFI/ryu/setting.py
Date: 2023-07-08 09:59:13
Description: 
'''
# setting.py
FACTOR = 0.9  # the coefficient of 'bw' , 1 - FACTOR is the coefficient of 'delay'

METHOD = 'dijkstra'  # the calculation method of shortest path

DISCOVERY_PERIOD = 10  # discover network structure's period, the unit is seconds.

MONITOR_PERIOD = 10  # monitor period, bw

DELAY_PERIOD = 10  # detector period, delay

SCHEDULE_PERIOD = 8  # shortest forwarding network awareness period

PRINT_SHOW = True     # show or not show print

"""
17  -----  27
['17', '15', '19', '8', '31', '12', '13', '27']
h17  :  iperf3 -c 10.0.0.27 -p 17027 -u -b 1.75M -t 20
h27  :  iperf3 -s -p 17027


11  -----  28
['11', '18', '24', '8', '31', '30', '29', '28']
h11  :  iperf3 -c 10.0.0.28 -p 11028 -u -b 1.75M -t 20
h28  :  iperf3 -s -p 11028

23 ----- 34
['23', '24', '8', '31', '33', '34']
h23  :  iperf3 -c 10.0.0.34 -p 23034 -u -b 1.75M -t 20
h34  :  iperf3 -s -p 23034


16 ----- 34
['16', '5', '8', '31', '33', '34']
h16  :  iperf3 -c 10.0.0.34 -p 16034 -u -b 1.75M -t 20
h34  :  iperf3 -s -p 



14  -----  13
['14', '30', '31', '12', '13']
h14  :  iperf3 -c 10.0.0.13 -p 14013 -u -b 1.75M -t 20
h13  :  iperf3 -s -p 14013

11 ----- 2
['11', '18', '24', '5', '7', '2']
h11  :  iperf3 -c 10.0.0.2 -p 11002 -u -b 1.75M -t 20
h2  :  iperf3 -s -p 11002


10 ----- 2
['10', '8', '5', '7', '2']
h10  :  iperf3 -c 10.0.0.2 -p 10002 -u -b 1.75M -t 20
h2  :  iperf3 -s -p 10002


1 ----- 25
['1', '4', '31', '33', '25']
h11  :  iperf3 -c 10.0.0.25 -p 1025 -u -b 1.75M -t 20
h2  :  iperf3 -s -p 1025


[0.91107872, 1.38268776, 1.82215743, 2.1995386 , 2.48911335,
2.67114764, 2.73323615, 2.67114764, 2.48911335, 2.1995386 ,
1.82215743, 1.38268776, 0.91107872, 1.09972234, 1.2755102 ,
1.42646267, 1.54229257, 1.61510629, 1.63994169, 1.61510629,
1.54229257, 1.42646267, 1.2755102 , 1.09972234]


 """