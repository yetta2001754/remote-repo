import torch
from torch import nn
import numpy as np
import time
import sys
import SignedAdam
import os
from utils import get_poison_tuples, load_pretrained_net
from dataloader import PoisonedDataset, FeatureSet
import torchvision
import torchvision.transforms as transforms

# PLEASE NOTE THAT: the order of the list must be preserved for the consistency of results!
COEFFS = {
    1: [0.4, 0.4, 0.1, 0.1, 0.0],  # Entropy: 1.72
    2: [0.8, 0.05, 0.05, 0.05, 0.05],  # 1.12
    3: [0.9, 0.025, 0.025, 0.025, 0.025],  # 0.67
    4: [0.6, 0.1, 0.1, 0.1, 0.1],  # 1.77
    5: [0.3, 0.3, 0.3, 0.05, 0.05],  # 2
    6: [0.3, 0.2, 0.2, 0.15, 0.15],  # 2.27
    7: [0.22, 0.2, 0.18, 0.17, 0.23],  # 2.31
    8: [0.2, 0.2, 0.2, 0.2, 0.2],  # 2.32
    9: [0.5, 0.3, 0.1, 0.05, 0.05],  # 1.79
    10: [0.5, 0.4, 0.02, 0.02, 0.06],  # 1.47
}


class PoisonBatch(torch.nn.Module):
    """
    Implementing this to work with PyTorch optimizers.
    """

    def __init__(self, base_list):
        super(PoisonBatch, self).__init__()
        base_batch = torch.stack(base_list, 0)
        self.poison = torch.nn.Parameter(base_batch.clone())

    def forward(self):
        return self.poison


def proj_onto_simplex(coeffs, psum=1.0):
    """
    Code stolen from https://github.com/hsnamkoong/robustopt/blob/master/src/simple_projections.py
    Project onto probability simplex by default.
    """
    v_np = coeffs.view(-1).detach().cpu().numpy()
    n_features = v_np.shape[0]
    v_sorted = np.sort(v_np)[::-1]
    cssv = np.cumsum(v_sorted) - psum
    ind = np.arange(n_features) + 1
    cond = v_sorted - cssv / ind > 0
    rho = ind[cond][-1]
    theta = cssv[cond][-1] / float(rho)
    w_ = np.maximum(v_np - theta, 0)
    return torch.Tensor(w_.reshape(coeffs.size())).to(coeffs.device)


def least_squares_simplex(A, b, x_init, tol=1e-6, verbose=False, device='cuda'):
    """
    The inner loop of Algorithm 1
    """
    m, n = A.size()
    assert b.size()[0] == A.size()[0], 'Matrix and vector do not have compatible dimensions'

    # Initialize the optimization variables
    if x_init is None:
        x = torch.zeros(n, 1).to(device)
    else:
        x = x_init

    # Define the objective function and its gradient
    f = lambda x: torch.norm(A.mm(x) - b).item()
    # change into a faster version when A is a tall matrix
    AtA = A.t().mm(A)
    Atb = A.t().mm(b)
    grad_f = lambda x: AtA.mm(x) - Atb
    # grad_f = lambda x: A.t().mm(A.mm(x)-b)

    # Estimate the spectral radius of the Matrix A'A
    y = torch.normal(0, torch.ones(n, 1)).to(device)
    lipschitz = torch.norm(A.t().mm(A.mm(y))) / torch.norm(y)

    # The stepsize for the problem should be 2/lipschits.  Our estimator might not be correct, it could be too small.  In
    # this case our learning rate will be too big, and so we need to have a backtracking line search to make sure things converge.
    t = 2 / lipschitz

    # Main iteration
    for iter in range(10000):
        x_hat = x - t * grad_f(x)  # Forward step:  Gradient decent on the objective term
        if f(x_hat) > f(x):  # Check whether the learning rate is small enough to decrease objective
            t = t / 2
        else:
            x_new = proj_onto_simplex(x_hat)  # Backward step: Project onto prob simplex
            stopping_condition = torch.norm(x - x_new) / max(torch.norm(x), 1e-8)
            if verbose: print('iter %d: error = %0.4e' % (iter, stopping_condition))
            if stopping_condition < tol:  # check stopping conditions
                break
            x = x_new

    return x


def loss_from_center(subs_net_list, target_feat_list, poison_batch, net_repeat, end2end,noise_level,random_seed):
    if end2end:
        loss = 0
        for net, center_feats in zip(subs_net_list, target_feat_list):
            if net_repeat > 1:
                poisons_feats_repeats = [net(x=poison_batch(), block=True) for _ in range(net_repeat)]
                BLOCK_NUM = len(poisons_feats_repeats[0])
                poisons_feats = []
                for block_idx in range(BLOCK_NUM):
                    poisons_feats.append(
                        sum([poisons_feat_r[block_idx] for poisons_feat_r in poisons_feats_repeats]) / net_repeat)
            elif net_repeat == 1:
                poisons_feats = net(x=poison_batch(), block=True)
            else:
                assert False, "net_repeat set to {}".format(net_repeat)

            net_loss = 0
            for pfeat, cfeat in zip(poisons_feats, center_feats):
                diff = torch.mean(pfeat, dim=0) - cfeat
                diff_norm = torch.norm(diff, dim=1) / torch.norm(cfeat, dim=1)
                net_loss += torch.mean(diff_norm)
            loss += net_loss / len(center_feats)
        loss = loss / len(subs_net_list)

    else:
        loss = 0
        for net, center in zip(subs_net_list, target_feat_list):
            poisons = [net(x=poison_batch(), penu=True) for _ in range(net_repeat)]

            poisons = sum(poisons) / len(poisons)

            if np.random.randint(low=0, high=100, size=1) > 0:  # 优化正确target
                torch.cuda.manual_seed(seed=random_seed)  # 用来固定随机噪声的序列 每个噪声训练的轮数
                random_noise = torch.randn(center.size()) * noise_level
                center = center +random_noise.to(center.device)

            diff = torch.mean(poisons, dim=0) - center
            diff_norm = torch.norm(diff, dim=1) / torch.norm(center, dim=1)
            loss += torch.mean(diff_norm)

        loss = loss / len(subs_net_list)

    return loss


# This is for when the coefficients are fixed, but not to 1/k. This is written originally to address the concerns
# raised by reviewers. We have plan to make it more comprehensive. As of now, it's just for linear transfer learning
# when net_repeat is set to one!
def loss_when_coeffs_fixed(subs_net_list, target_feat_list, poison_batch, coeffs, net_repeat=1, end2end=False):
    assert net_repeat == 1 and end2end == False

    loss = 0
    for net, center in zip(subs_net_list, target_feat_list):
        poisons = net(x=poison_batch(), penu=True)
        diff = torch.sum(coeffs * poisons, dim=0) - center
        diff_norm = torch.norm(diff, dim=1) / torch.norm(center, dim=1)
        loss += torch.mean(diff_norm)

    loss = loss / len(subs_net_list)

    return loss


def get_CP_loss(net_list, target_feature_list, poison_batch, s_coeff_list, net_repeat, tol=1e-6,random_seed=1,noise_level=0.01):
    """
    Corresponding to one step of the outer loop (except for updating and clipping) of Algorithm 1
    """
    # assert len(net_list) == 1 or net_repeat == 3
    poison_feat_mat_list = []
    for net in net_list:
        if net_repeat > 1:
            poisons = [net(x=poison_batch(), penu=True) for _ in range(net_repeat)]
            poisons = sum(poisons) / len(poisons)
        elif net_repeat == 1:
            poisons = net(x=poison_batch(), penu=True)
        else:
            assert False
        poison_feat_mat_list.append(poisons)

    t = time.time()
    for nn, (pfeat_mat, target_feat) in enumerate(zip(poison_feat_mat_list, target_feature_list)):



        # 在target feature 上添加随机噪声
        if np.random.randint(low=0, high=100, size=1) > 0:#优化正确target
            torch.cuda.manual_seed(seed=random_seed)# 用来固定随机噪声的序列 每个噪声训练的轮数
            random_noise = torch.randn(target_feat.size())*noise_level
            target_feat=target_feat+random_noise.to(target_feat.device)





        s_coeff_list[nn] = least_squares_simplex(A=pfeat_mat.t().detach(), b=target_feat.t().detach(),
                                                 x_init=s_coeff_list[nn], tol=tol)
    coeffs_time = int(time.time() - t)

    total_loss = 0
    for net, s_coeff, target_feat, poison_feat_mat in zip(net_list, s_coeff_list, target_feature_list,
                                                          poison_feat_mat_list):
        residual = target_feat - torch.sum(s_coeff * poison_feat_mat, 0, keepdim=True)
        target_norm_square = torch.sum(target_feat ** 2)
        recon_loss = 0.5 * torch.sum(residual ** 2) / target_norm_square

        total_loss += recon_loss

    total_loss = total_loss / len(net_list)

    return total_loss, s_coeff_list, coeffs_time


def get_CP_loss_end2end(net_list, target_feature_list, poison_batch, s_coeff_list, net_repeat, tol=1e-6):
    """
    Corresponding to one step of the outer loop (except for updating and clipping) of Algorithm 1
    """
    poison_feat_mat_list = [net(x=poison_batch(), block=True) for net in net_list]

    total_loss = 0

    for nn, (net, target_feats, poison_feats) in enumerate(zip(net_list, target_feature_list, poison_feat_mat_list)):
        total_loss_tmp = 0
        for n_block, (pfeat, tfeat) in enumerate(zip(poison_feats, target_feats)):
            t = time.time()
            s_coeff_list[nn][n_block] = least_squares_simplex(A=pfeat.view(pfeat.size(0), -1).t().detach(),
                                                              b=tfeat.view(-1, 1).detach(),
                                                              x_init=s_coeff_list[nn][n_block], tol=tol)
            coeffs_time = int(time.time() - t)

            residual = tfeat - torch.sum(s_coeff_list[nn][n_block].unsqueeze(2).unsqueeze(3) * pfeat, 0, keepdim=True)
            target_norm_square = torch.sum(tfeat ** 2)
            recon_loss = 0.5 * torch.sum(residual ** 2) / target_norm_square

            total_loss_tmp += recon_loss
        total_loss += total_loss_tmp / len(poison_feats)

    total_loss = total_loss / len(net_list)

    return total_loss, s_coeff_list, coeffs_time


def make_convex_polytope_poisons(subs_net_list, target_net, base_tensor_list, target, targets_net,device, args, opt_method='adam',
                                 lr=0.1, momentum=0.9, iterations=4000, epsilon=0.1,
                                 decay_ites=[10000, 15000], decay_ratio=0.1,
                                 mean=torch.Tensor((0.4914, 0.4822, 0.4465)).reshape(1, 3, 1, 1),
                                 std=torch.Tensor((0.2023, 0.1994, 0.2010)).reshape(1, 3, 1, 1),
                                 chk_path='', poison_idxes=[], poison_label=-1,
                                 tol=1e-6, start_ite=0, poison_init=None, end2end=False, mode='convex',
                                 net_repeat=1,noise_level=0.01):
    target_net.eval()

    poison_batch = PoisonBatch(poison_init).to(device)

    opt_method = opt_method.lower()
    if opt_method == 'sgd':
        optimizer = torch.optim.SGD(poison_batch.parameters(), lr=lr, momentum=momentum)
    elif opt_method == 'signedadam':
        optimizer = SignedAdam.SignedAdam(poison_batch.parameters(), lr=lr, betas=(momentum, 0.999))
        print("Using Signed Adam")
    elif opt_method == 'adam':
        optimizer = torch.optim.Adam(poison_batch.parameters(), lr=lr, betas=(momentum, 0.999))
    target = target.to(device)
    std, mean = std.to(device), mean.to(device)
    base_tensor_batch = torch.stack(base_tensor_list, 0)
    base_range01_batch = base_tensor_batch * std + mean

    # Because we have turned on DP for the substitute networks,
    # the target image's feature becomes random.
    # We can try enforcing the convex polytope in one of the multiple realizations of the feature,
    # but empirically one realization is enough.
    target_feat_list = []
    # Coefficients for the convex combination.
    # Initializing from the coefficients of last step gives faster convergence.
    s_init_coeff_list = []
    n_poisons = len(base_tensor_list)
    for n, net in enumerate(subs_net_list):
        net.eval()
        if end2end:
            block_feats = [feat.detach() for feat in net(x=target, block=True)]
            target_feat_list.append(block_feats)
            s_coeff = [torch.ones(n_poisons, 1).to(device) / n_poisons for _ in range(len(block_feats))]
        else:
            target_feat_list.append(net(x=target, penu=True).detach())
            s_coeff = torch.ones(n_poisons, 1).to(device) / n_poisons

        s_init_coeff_list.append(s_coeff)

    # Keep this for evaluation.
    if end2end:
        target_feat_in_target = [feat.detach() for feat in target_net(x=target, block=True)]
        target_init_coeff = [[torch.ones(len(base_tensor_list), 1).to(device) / n_poisons
                              for _ in range(len(target_feat_in_target))]]
    else:
        target_feat_in_target = target_net(x=target, penu=True).detach()
        target_init_coeff = [torch.ones(len(base_tensor_list), 1).to(device) / n_poisons]

    cp_loss_func = get_CP_loss_end2end if end2end else get_CP_loss

    coeffs_time = 0
    poisons_time = 0
    for ite in range(start_ite, iterations):
        if ite in decay_ites:
            for param_group in optimizer.param_groups:
                param_group['lr'] *= decay_ratio
            print("%s Iteration %d, Adjusted lr to %.2e" % (time.strftime("%Y-%m-%d %H:%M:%S"), ite, lr))

        poison_batch.zero_grad()
        t = time.time()
        if mode == 'convex':
            total_loss, s_init_coeff_list, coeffs_time_tmp = cp_loss_func(subs_net_list, target_feat_list, poison_batch,
                                                                          s_init_coeff_list,
                                                                          net_repeat=net_repeat,
                                                                          tol=tol)
        elif mode == 'mean':
            #random seed shengcheng
            random_seed = [0]
            if ite % 1 == 0:#修改
                random_seed = torch.randint(100, size=[1])

            total_loss = loss_from_center(subs_net_list, target_feat_list, poison_batch, net_repeat, end2end,noise_level=noise_level,random_seed=random_seed[0])
            coeffs_time_tmp = 0

        elif mode.startswith('coeffs_fixed_type_'):
            coeffs_type = int(mode.split("coeffs_fixed_type_")[1])
            coeffs = COEFFS[coeffs_type]
            random.shuffle(coeffs)
            coeffs = torch.Tensor([coeffs]).t().to(device)
            assert abs(sum(coeffs).item() - 1.0) < 10e-3, print(sum(coeffs).item())
            if ite == start_ite:
                print("coeffs fixed to: {}".format(coeffs))
            total_loss = loss_when_coeffs_fixed(subs_net_list, target_feat_list, poison_batch, coeffs, net_repeat,
                                                end2end)
            coeffs_time_tmp = 0

        coeffs_time += coeffs_time_tmp

        total_loss.backward()
        optimizer.step()
        poisons_time += int(time.time() - t)

        # clip the perturbations into the range
        assert epsilon == 0.1
        perturb_range01 = torch.clamp((poison_batch.poison.data - base_tensor_batch) * std, -epsilon, epsilon)
        perturbed_range01 = torch.clamp(base_range01_batch.data + perturb_range01.data, 0, 1)
        poison_batch.poison.data = (perturbed_range01 - mean) / std

        if ite % 50 == 0 or ite == iterations - 1:
            # whether we are doing convex or mean mode, we want to see the convex loss function for the target victim.
            # Note this unification has done after running the attack for convex method and mean method (0-74), i.e.,
            # for convex 0-99 and mean 0-74 the "loss in target network" is showing different losses for convex vs. mean
            target_loss, target_init_coeff, _ = cp_loss_func([target_net],
                                                             [target_feat_in_target],
                                                             poison_batch,
                                                             target_init_coeff,
                                                             net_repeat=1,
                                                             tol=tol)

            # compute the difference in target
            print(" %s Iteration %d \t Training Loss: %.3e \t Loss in Target Net: %.3e\t  " % (
                time.strftime("%Y-%m-%d %H:%M:%S"), ite, total_loss.item(), target_loss.item()))
            sys.stdout.flush()

            # save the checkpoints
            poison_tuple_list = get_poison_tuples(poison_batch, poison_label)
            torch.save({'poison': poison_tuple_list, 'idx': poison_idxes, 'coeffs_time': coeffs_time,
                        'poisons_time': poisons_time, 'target_loss': target_loss, 'total_loss': total_loss,
                        'coeff_list': s_init_coeff_list, 'coeff_list_in_victim': target_init_coeff},
                       os.path.join(chk_path, "poison_%05d.pth" % ite))

        # evaluate the
        if ite > 0:
            if ite % 500 == 0 or ite == iterations - 1 :

                # 重新加载模型
                poison_tuple_list = get_poison_tuples(poison_batch, poison_label)
                targets_net_reload = []
                for tnet in args.target_net:
                    target_net = load_pretrained_net(tnet, args.test_chk_name, model_chk_path=args.model_resume_path)
                    targets_net_reload.append(target_net)
                ###########################################

                tt = time.time()
                res = []
                print("Evaluating against victims networks")
                for tnet, tnet_name in zip(targets_net_reload, args.target_net):
                    print(tnet_name)
                    pred = train_network_with_poison(tnet, target, poison_tuple_list, poison_idxes, chk_path, args,
                                                     save_state=False)
                    res.append(pred)
                    print("--------")

                print("------SUMMARY------")
                print("TIME ELAPSED (mins): {}".format(int((tt - t) / 60)))
                print("TARGET INDEX: {}".format(args.target_index))
                for tnet_name, r in zip(args.target_net, res):
                    print(tnet_name, int(r == args.poison_label))



    return get_poison_tuples(poison_batch, poison_label)


class AverageMeter(object):
    """Computes and stores the average and current value"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count


def accuracy(output, target, topk=(1,)):
    """Computes the precision@k for the specified values of k"""
    with torch.no_grad():
        maxk = max(topk)
        batch_size = target.size(0)

        _, pred = output.topk(maxk, 1, True, True)
        pred = pred.t()
        correct = pred.eq(target.view(1, -1).expand_as(pred))

        res = []
        for k in topk:
            correct_k = correct[:k].view(-1).float().sum(0, keepdim=True)
            res.append(correct_k.mul_(100.0 / batch_size))
        return res

def SoftLabelNLL(predicted, target, reduce=False):
    if reduce:
        return -(target * predicted).sum(dim=1).mean()
    else:
        return -(target * predicted).sum(dim=1)


def train_network_with_poison(net, target_img, poison_tuple_list, base_idx_list, chk_path, args, save_state=False):
    # requires implementing a get_penultimate_params_list() method to get the parameter identifier of the net's last layer
    if args.end2end:
        params = net.parameters()
    else:
        params = net.module.get_penultimate_params_list()

    if args.retrain_opt == 'adam':
        print("Using Adam for retraining")
        optimizer = torch.optim.Adam(params, lr=args.retrain_lr, weight_decay=args.retrain_wd)
    else:
        print("Using SGD for retraining")
        optimizer = torch.optim.SGD(params, lr=args.retrain_lr, momentum=args.retrain_momentum,
                                    weight_decay=args.retrain_wd)

    net.eval()

    criterion = nn.CrossEntropyLoss().to('cuda')

    # Create the poisoned dataset
    transform_train = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
    ])
    transform_test = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
    ])
    poisoned_dset = PoisonedDataset(args.train_data_path, subset='others', transform=transform_train,
                                    num_per_label=args.num_per_class, poison_tuple_list=poison_tuple_list,
                                    poison_indices=base_idx_list, subset_group=args.subset_group)

    poisoned_loader = torch.utils.data.DataLoader(poisoned_dset, batch_size=args.retrain_bsize, shuffle=True)

    # The test set of clean CIFAR10
    testset = torchvision.datasets.CIFAR10(root=args.dset_path, train=False, download=True, transform=transform_test)
    test_loader = torch.utils.data.DataLoader(testset, batch_size=500)

    if not args.end2end:
        # create a dataloader that returns the features
        poisoned_loader = torch.utils.data.DataLoader(FeatureSet(poisoned_loader, net, device=args.device),
                                                      batch_size=64, shuffle=True)


    #smooth coeff

    smoothing_coef=0.05
    augmented_smooth=False


    for epoch in range(args.retrain_epochs):
        net.eval()
        loss_meter = AverageMeter()
        acc_meter = AverageMeter()
        time_meter = AverageMeter()

        if epoch in args.lr_decay_epoch:
            for param_group in optimizer.param_groups:
                param_group['lr'] *= 0.1

        end_time = time.time()
        for ite, (input, target) in enumerate(poisoned_loader):
            input, target = input.to('cuda'), target.to('cuda')

            # aug!!!
            if augmented_smooth:
                b_y_one_hot = (torch.zeros(input.shape[0], 10, dtype=torch.float).to('cuda')).scatter_(1,target.view(-1,1),1)
                aug_target = (1 - smoothing_coef) * b_y_one_hot + (smoothing_coef / 10)  #

            if args.end2end:
                feat = net.module.penultimate(input)
            else:
                feat = input
            output = net.module.linear(feat)
            # aug!!!
            if augmented_smooth:
                loss = SoftLabelNLL(output, aug_target, reduce=True)
            else:
                loss = criterion(output, target)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            prec1 = accuracy(output, target)[0]

            time_meter.update(time.time() - end_time)
            end_time = time.time()
            loss_meter.update(loss.item(), input.size(0))
            acc_meter.update(prec1.item(), input.size(0))

            if epoch % 30 == 0 and (ite == len(poisoned_loader) - 1):
                print("{2}, Epoch {0}, Iteration {1}, loss {loss.val:.3f} ({loss.avg:.3f}), "
                      "acc {acc.val:.3f} ({acc.avg:.3f})".
                      format(epoch, ite, time.strftime("%Y-%m-%d %H:%M:%S"),
                             loss=loss_meter, acc=acc_meter))
            sys.stdout.flush()

        if epoch == args.retrain_epochs - 1:
            # print the scores for target and base
            target_pred = net(target_img.to('cuda'))
            score, pred = target_pred.topk(1, 1, True, True)
            poison_pred_list = []
            for poison_img, _ in poison_tuple_list:
                base_scores = net(poison_img[None, :, :, :].to('cuda'))
                base_score, base_pred = base_scores.topk(1, 1, True, True)
                poison_pred_list.append(base_pred.item())
            print(
                "Target Label: {}, Poison label: {}, Prediction:{}, Target's Score:{}, Poisons' Predictions:{}".format(
                    args.target_label, args.poison_label, pred[0][0].item(),
                    list(target_pred.detach().view(-1).cpu().numpy()),
                    poison_pred_list))

    # Evaluate the results on the clean test set
    val_acc_meter = AverageMeter()
    with torch.no_grad():
        for ite, (input, target) in enumerate(test_loader):
            input, target = input.to('cuda'), target.to('cuda')

            output = net(input)

            prec1 = accuracy(output, target)[0]
            val_acc_meter.update(prec1.item(), input.size(0))

            if False or ite % 100 == 0 or ite == len(test_loader) - 1:
                print("{2} Epoch {0}, Val iteration {1}, "
                      "acc {acc.val:.3f} ({acc.avg:.3f})".
                      format(epoch, ite, time.strftime("%Y-%m-%d %H:%M:%S"), acc=val_acc_meter))

    if save_state:
        state_dict = {"state_dict": net.state_dict(), "epoch": epoch, "acc": val_acc_meter.avg}
        torch.save(state_dict, os.path.join(chk_path, 'last_epoch.pth'))

    print("* Prec: {}".format(val_acc_meter.avg))
    return pred[0][0].item()
