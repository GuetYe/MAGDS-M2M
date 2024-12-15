'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN-WIFI/rl/sac_train.py
Date: 2024-03-06 20:47:00
Description: 
'''

import sys
import os

curr_path = os.path.dirname(os.path.abspath(__file__))  # 当前文件所在绝对路径
parent_path = os.path.dirname(curr_path)  # 父路径
sys.path.append(parent_path)  # 添加路径到系统路径
# sys.path.append(os.path.abspath(os.path.join(__file__, "..", "..")))

import datetime

from sac import SAC_Config,SAC
from common.utils import plot_rewards
from common.utils import save_results,make_dir,plot_test_rewards


import config
from dataset import file_path_yield, read_pickle
from rl.env import Environment


curr_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") # 获取当前时间




def train(cfg,env,agent):

    print(f'环境:{cfg.env_name}, 算法:{cfg.algo_name}, 设备:{cfg.device}')

    rewards = []  # 记录奖励
    ma_rewards = [] # 记录滑动平均奖励
    for i_ep in range(cfg.train_eps):
        for index, pkl_path in enumerate(file_path_yield(config.FILE_DIR, ista=1, iend=120, step=10)):
            ep_reward = 0  # 记录每个回合的奖励
            pkl_graph = read_pickle(pkl_path)
            c = config.c
            for _src, _dst in config.SRC_DST:
                env.update_pkl_graph(pkl_graph)  # 更新环境里的pkl_graph去生成新的TM
                state = env.reset(_src, _dst, c)

                while True:
                    action = agent.choose_action(state)  # 根据算法选择一个动作
                    next_state, reward, done, _ , path_info= env.step(action)  # based-free , agent与环境进行一次动作交互
                    agent.memory.push(state, action, reward,next_state, done)  # 保存transition
                    state = next_state  # 更新状态
                    ep_reward += reward # 累加奖励
                    if agent.memory.size() > cfg.minimal_size:
                        b_state, b_action, b_reward, b_next_state, b_done = agent.memory.sample(cfg.batch_size)
                        transition_dict = {'states': b_state, 'actions': b_action, 'next_states': b_next_state, 'rewards': b_reward, 'dones': b_done}
                        agent.update(transition_dict)                    
                    if done or path_info['step_num'] > 200:
                    # if done :
                        break

            rewards.append(ep_reward)

            if ma_rewards:
                ma_rewards.append(ma_rewards[-1]*0.9+ep_reward*0.1)
            else:
                ma_rewards.append(ep_reward)

            break   #这个break是for index, pkl_path in enumerate的


        if i_ep%100 == 0 :
            print("回合数：{}/{}，奖励{:.1f} , len_path={}, path={} ".format(i_ep+1, cfg.train_eps, ep_reward, len(path_info['path']), path_info))
    # env.close() 
    return rewards,ma_rewards,path_info



if __name__=='__main__':

    cfg = SAC_Config() #实例化配置
    env = Environment()
    agent = SAC(state_dim = config.STATE_DIM + config.MPLS_MAX, hidden_dim=512 , action_dim=config.ACTION_DIM, cfg=cfg)


    make_dir(cfg.result_path, cfg.model_path)  # 创建保存结果和模型路径的文件夹

    
    # 训练
    rewards, ma_rewards, path_info = train(cfg, env, agent)#训练
    agent.save(path=cfg.model_path)  # 保存模型
    save_results(rewards, ma_rewards, tag='train',path=cfg.result_path)  # 保存结果
    plot_rewards(rewards, ma_rewards, cfg, tag="train")  # 画出结果
    