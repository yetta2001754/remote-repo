# _*_ coding:utf-8_*_
# 开发人员：jinyaoyu
# 开发时间：2022/10/2716:06
# 文件名称：fetch_res.py.py
# 开发工具：PyCharm

import numpy as np
import re
import os
import pandas as pd


path = 'D:\jyy\BullseyePoison-master-noise\\res\pi800_pn5_noise0.3_if0_ran1.txt'
data = []
start_line = []
time = []
target = []
DPN92 = []
SENet18 = []
ResNet50 = []
ResNeXt29_2x64d = []
GoogLeNet = []
MobileNetV2 = []
ResNet18 = []
DenseNet121 = []

with open(path,mode='r',encoding='utf-8') as f:
    for line in f.readlines():
        if re.findall("------SUMMARY------",line):
            start_line.append(line)
        if re.findall("TIME ELAPSED",line):
            time.append(line[-2])
        if re.match("TARGET INDEX: +\d{1}",line):
            target.append(line[14:-1])
        if re.match("DPN92 +\d{1}",line):
            DPN92.append(line[-2])
        if re.match("SENet18 +\d{1}",line):
            SENet18.append(line[-2])
        if re.match("ResNet50 +\d{1}",line):
            ResNet50.append(line[-2])
        if re.match("ResNeXt29_2x64d +\d{1}",line):
            ResNeXt29_2x64d.append(line[-2])
        if re.match("GoogLeNet +\d{1}",line):
            GoogLeNet.append(line[-2])
        if re.match("MobileNetV2 +\d{1}",line):
            MobileNetV2.append(line[-2])
        if re.match("ResNet18 +\d{1}",line):
            ResNet18.append(line[-2])
        if re.match("DenseNet121 +\d{1}",line):
            DenseNet121.append(line[-2])

dict = {
        "DPN92":DPN92,
        "SENet18":SENet18,
        "ResNet50":ResNet50,
        "ResNeXt29_2x64d":ResNeXt29_2x64d,
        "GoogLeNet":GoogLeNet,
        "MobileNetV2":MobileNetV2,
        "ResNet18":ResNet18,
        "DenseNet121":DenseNet121}

df = pd.DataFrame(dict).astype(int)

df1 = df[df.index%2 == 1]
# df1.loc['success_rate'] = df1.apply(lambda x: sum(x)/50,axis=0)
# df500 = df[df.index%8 == 0]
# df1000 = df[df.index%8 == 1]
# df1500 = df[df.index%8 == 2]
# df2000 = df[df.index%8 == 3]
# df2500 = df[df.index%8 == 4]
# df3000 = df[df.index%8 == 5]
# df3500 = df[df.index%8 == 6]
# df4000 = df[df.index%8 == 7]


# df500.loc["sum"]=df500.apply(lambda x:sum(x)/50,axis=0)
# df1000.loc["sum"]=df1000.apply(lambda x:sum(x)/50,axis=0)
# df1500.loc["sum"]=df1500.apply(lambda x:sum(x)/50,axis=0)
# df2000.loc["sum"]=df2000.apply(lambda x:sum(x)/50,axis=0)
# df2500.loc["sum"]=df2500.apply(lambda x:sum(x)/50,axis=0)
# df3000.loc["sum"]=df3000.apply(lambda x:sum(x)/50,axis=0)
# df3500.loc["sum"]=df3500.apply(lambda x:sum(x)/50,axis=0)
# df4000.loc["sum"]=df4000.apply(lambda x:sum(x)/50,axis=0)

list = ['DPN92','SENet18','ResNet50','ResNeXt29_2x64d','GoogLeNet','MobileNetV2','ResNet18','DenseNet121']
# df2 = pd.DataFrame({"500":df500.loc['sum'],"1000":df1000.loc['sum'],"1500":df1500.loc['sum'],"2000":df2000.loc['sum'],"2500":df2500.loc['sum'],"3000":df3000.loc['sum'],"3500":df3500.loc['sum'],"4000":df4000.loc['sum']})





df.to_csv('./res/pi4000_pn5_noise0.01___try.csv')










