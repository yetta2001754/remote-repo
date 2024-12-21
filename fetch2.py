
import numpy as np
import re
import os

import pandas as pd

score_line = []

path_BP_1 = 'D:\jyy\BullseyePoison-master\\res\pi800_pn5_noise0_1.txt'
path_BP_2 = 'D:\jyy\BullseyePoison-master\\res\pi800_pn5_noise0_2.txt'
path_BP_3 = 'D:\jyy\BullseyePoison-master\\res\pi800_pn5_noise0_3.txt'
path_n001 = 'D:\jyy\BullseyePoison-master-noise\\res\pi800_pn5_noise0.001_if0_ran1.txt'
path_n01 = 'D:\jyy\BullseyePoison-master-noise\\res\pi800_pn5_noise0.01_if0_ran1.txt'
path_n1 = 'D:\jyy\BullseyePoison-master-noise\\res\pi800_pn5_noise0.1_if0_ran1.txt'
path_n3 ='D:\jyy\BullseyePoison-master-noise\\res\pi800_pn5_noise0.3_if0_ran1.txt'
path = 'D:\jyy\BullseyePoison-master-noise\\res\pi800_pn5_noise0.5_if0_ran1.txt'

# with open(path_BP_3,mode='r',encoding='utf-8') as f:
#     for line in f.readlines():
#         if re.findall("Target Label: 6, Poison label: ",line):
#             score_line.append(line)
#
# DPN92 = score_line[0:399:8]
# SENet18 = score_line[1:399:8]
# ResNet50 = score_line[2:399:8]
# ResNeXt29_2x64d = score_line[3:399:8]
# GoogLeNet =  score_line[4:399:8]
# MobileNetV2 =  score_line[5:399:8]
# ResNet18 =  score_line[6:399:8]
# DenseNet121 =  score_line[7:400:8]
#
# Prediction = []
# pre = []
# Target_score = []
# Target_score_6 = []
# Target_score_8 = []
# D_value = []
# for i in range(50):
#     pre = DenseNet121[i]
#     pre= pre[pre.rfind("Prediction:"):]
#     pre = pre[:pre.rfind(", Target's Score:")]
#     pre = pre.strip("Prediction:")
#     if int(pre)==8:
#         pre = 1
#     else:
#         pre = 0
#     Prediction.append(pre)
#
#     ts = DenseNet121[i]
#     ts = ts[ts.rfind("Target's Score:["):]
#     ts = ts[:ts.rfind(", Poisons' Predictions:")]
#     ts = ts.strip("Target's Score:[").strip(']')
#     ts = ts.split(",")
#     Target_score.append(ts)
#     Target_score_6.append(float(Target_score[i][6]))
#     Target_score_8.append(float(Target_score[i][8]))
#     D_value.append(float(Target_score[i][6])-float(Target_score[i][8]))
#
#
#
# dict = {"Prediction":Prediction,
#         "Target_score_6":Target_score_6,
#         "Target_score_8":Target_score_8,
#         "6-8":D_value}
# df = pd.DataFrame(dict)










with open(path,mode='r',encoding='utf-8') as f:
    for line in f.readlines():
        if re.findall("Target Label: 6, Poison label: ",line):
            score_line.append(line)

DPN92 = score_line[8:799:16]
SENet18 = score_line[9:799:16]
ResNet50 = score_line[10:799:16]
ResNeXt29_2x64d = score_line[11:799:16]
GoogLeNet =  score_line[12:799:16]
MobileNetV2 =  score_line[13:799:16]
ResNet18 =  score_line[14:799:16]
DenseNet121 =  score_line[15:800:16]

Prediction = []
pre = []
Target_score = []
Target_score_6 = []
Target_score_8 = []
D_value = []
for i in range(50):
    pre = DenseNet121[i]
    pre= pre[pre.rfind("Prediction:"):]
    pre = pre[:pre.rfind(", Target's Score:")]
    pre = pre.strip("Prediction:")
    if int(pre)==8:
        pre = 1
    else:
        pre = 0
    Prediction.append(pre)

    ts = DenseNet121[i]
    ts = ts[ts.rfind("Target's Score:["):]
    ts = ts[:ts.rfind(", Poisons' Predictions:")]
    ts = ts.strip("Target's Score:[").strip(']')
    ts = ts.split(",")
    Target_score.append(ts)
    Target_score_6.append(float(Target_score[i][6]))
    Target_score_8.append(float(Target_score[i][8]))
    D_value.append(float(Target_score[i][6])-float(Target_score[i][8]))



dict = {"Prediction":Prediction,
        "Target_score_6":Target_score_6,
        "Target_score_8":Target_score_8,
        "6-8":D_value}
df = pd.DataFrame(dict)

print(score_line)