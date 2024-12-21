#!/usr/bin/env bash
python craft_poisons_transfer.py --gpu $1 --mode $2 --target-index $3 --net-repeat $4 --subs-chk-name ckpt-%s-4800-dp0.200-droplayer0.000-seed1226.t7 ckpt-%s-4800-dp0.250-droplayer0.000-seed1226.t7 ckpt-%s-4800-dp0.300-droplayer0.000.t7 --subs-dp 0.2 0.25 0.3  --substitute-nets DPN92 SENet18 ResNet50 ResNeXt29_2x64d GoogLeNet MobileNetV2 --target-label 6 --poison-label 8 --target-net DPN92 SENet18 ResNet50 ResNeXt29_2x64d GoogLeNet MobileNetV2 ResNet18 DenseNet121 --chk-path attack-results-10poisons/100-overlap/linear-transfer-learning --poison-ites 800 --poison-epsilon 0.1 --poison-num 5