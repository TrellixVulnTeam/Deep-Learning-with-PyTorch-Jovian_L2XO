# -*- coding: utf-8 -*-
"""6. Data Augmentation, ResNets, and Regularization.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1dVnycuEanOVx61atVkvxeSVnOQXlXME7

# Imports
"""

# Commented out IPython magic to ensure Python compatibility.
import os
import tarfile

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torch.utils.data import random_split

from torchvision.utils import make_grid
from torchvision.datasets.utils import download_url
from torchvision.datasets import ImageFolder
import torchvision.transforms as tt

import numpy as np

import matplotlib
import matplotlib.pyplot as plt
# %matplotlib inline

"""# Download and Prepare Dataset"""

DOWNLOAD_URL = "https://s3.amazonaws.com/fast-ai-imageclas/cifar10.tgz"
download_url(DOWNLOAD_URL, ".")

with tarfile.open("./cifar10.tgz", "r:gz") as tar:
  def is_within_directory(directory, target):
      
      abs_directory = os.path.abspath(directory)
      abs_target = os.path.abspath(target)
  
      prefix = os.path.commonprefix([abs_directory, abs_target])
      
      return prefix == abs_directory
  
  def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
  
      for member in tar.getmembers():
          member_path = os.path.join(path, member.name)
          if not is_within_directory(path, member_path):
              raise Exception("Attempted Path Traversal in Tar File")
  
      tar.extractall(path, members, numeric_owner=numeric_owner) 
      
  
  safe_extract(tar, path="./data")

DATA_DIR = "data/cifar10"
print(os.listdir(DATA_DIR))
classes = os.listdir(DATA_DIR + "/train")
print(classes)

"""### Visualize Channel Distribution and Get Stats"""

dataset = ImageFolder(DATA_DIR + "/train", transform=tt.ToTensor())

images = [image for (image, _) in dataset]
images = torch.stack(images)
images.shape

images = images.permute(1, 0, 2, 3)
images.shape

images = images.reshape(3, -1)
images.shape

channel1, channel2, channel3 = [channel.numpy() for channel in images]
len(channel1), len(channel2), len(channel3)

figure, ax = plt.subplots(nrows=2, ncols=2, sharex=True, sharey=True, figsize=(12, 6))
# figure.set_size_inches((12, 6))

hist1 = ax[0, 0].hist(channel1, bins=100, color="red")
hist2 = ax[0, 0].hist(channel2, bins=100, color="green")
hist3 = ax[0, 0].hist(channel3, bins=100, color="blue")

hist1 = ax[0, 1].hist(channel1, bins=100, color="red")
hist2 = ax[1, 0].hist(channel2, bins=100, color="green")
hist3 = ax[1, 1].hist(channel3, bins=100, color="blue")

stats_mean = [image.mean() for image in images]
stats_std = [image.std() for image in images]

calc_stats = (tuple(stats_mean), tuple(stats_std))
calc_stats

"""### Data Transforms (Augmentation and Normalization)"""

given_stats = ((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))
stats = calc_stats

train_tfms = tt.Compose([tt.RandomCrop((32,32), padding=4, padding_mode="reflect"),
                        tt.RandomHorizontalFlip(p=0.5),
                        # tt.RandomRotate
                        # tt.RandomResizedCrop(256, scale=(0.5,0.9), ratio=(1, 1)), 
                        # tt.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1, hue=0.1),
                        tt.ToTensor(),
                        tt.Normalize(*stats, inplace=True)])

val_tfms = tt.Compose([tt.ToTensor(), tt.Normalize(*stats, inplace=True)])

"""### ImageFolder and DataLoader"""

train_ds = ImageFolder(DATA_DIR + "/train", train_tfms)
val_ds = ImageFolder(DATA_DIR + "/test", val_tfms)

BATCH_SIZE = 128

train_dl = DataLoader(train_ds, BATCH_SIZE, shuffle=True, num_workers=2, pin_memory=True)
val_dl = DataLoader(val_ds, BATCH_SIZE, num_workers=2, pin_memory=True)

def denormalize(image, means, stds):
  means = torch.tensor(means).reshape(1, 3, 1, 1)
  stds = torch.tensor(stds).reshape(1, 3, 1, 1)
  return image * stds + means

def show_batch(dl):
  for images, _ in dl:
    figure, ax = plt.subplots(figsize=(16, 16))
    ax.set_xticks([]); ax.set_yticks([])
    denorm_images = denormalize(images, *stats)
    plt.imshow(make_grid(denorm_images, nrow=16).permute(1, 2, 0).clip(0, 1))
    break

show_batch(train_dl)

"""# Using a GPU"""

def get_device():
  """Pick GPU if GPU is available, else pick CPU"""
  if torch.cuda.is_available():
    return torch.device("cuda")
  else:
    return torch.device("cpu")

device = get_device()
print(device)

def to_device(data, device):
  """Move Tensors to specified device"""
  if isinstance(data, (list, tuple)):
    return [to_device(x, device) for x in data]
  return data.to(device, non_blocking=True)

class DeviceDataLoader():
  """Wrap a dataloader to move data to a device"""
  def __init__(self, dl, device):
    self.dl = dl
    self.device = device

  def __iter__(self):
    """Yield a batch of data after moving it to device"""
    for batch in self.dl:
      yield to_device(batch, self.device)

  def __len__(self):
    """Returns the number of batches in the dataloader"""
    return len(self.dl)

train_loader = DeviceDataLoader(train_dl, device)
val_loader = DeviceDataLoader(val_dl, device)

"""# Model"""

def accuracy(outputs, labels):
  _, preds = torch.max(outputs, dim=1)
  return torch.tensor(torch.sum(preds == labels).item() / len(preds))

class ImageClassificationBase(nn.Module):
  def training_step(self, batch):
    images, labels = batch
    out = self(images)
    loss = F.cross_entropy(out, labels)
    return loss

  def validation_step(self, batch):
    images, labels = batch
    out = self(images)
    loss = F.cross_entropy(out, labels)
    acc = accuracy(out, labels)
    return {"val_loss": loss, "val_acc": acc}

  def validation_epoch_end(self, outputs):
    batch_losses = [x["val_loss"] for x in outputs]
    epoch_loss = torch.stack(batch_losses).mean()
    batch_accs = [x["val_acc"] for x in outputs]
    epoch_acc = torch.stack(batch_accs).mean()
    return {"val_loss": epoch_loss.item(), "val_acc": epoch_acc.item()}

  def epoch_end(self, epoch, result):
    print("Epoch [{}], last_lr: {:.5f}, train_loss: {:.4f} val_Loss: {:.4f}, val_Acc: {:.4f}".format(
        epoch,
        result["lrs"][-1],
        result["train_loss"],
        result["val_loss"],
        result["val_acc"]))

def conv_block(in_channels, out_channels, pool=False):
  layers = [nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, stride=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)]
  if pool: layers.append(nn.MaxPool2d(2))  # default stride == kernel_size
  return nn.Sequential(*layers)

class ResNet9(ImageClassificationBase):
  def __init__(self, in_channels, num_classes):
    super().__init__()

    self.conv1 = conv_block(in_channels, 64)
    self.conv2 = conv_block(64, 128, pool=True)
    self.res1 = nn.Sequential(conv_block(128, 128), conv_block(128, 128))

    self.conv3 = conv_block(128, 256, pool=True)
    self.conv4 = conv_block(256, 512, pool=True)
    self.res2 = nn.Sequential(conv_block(512, 512), conv_block(512, 512))

    self.classifier = nn.Sequential(nn.MaxPool2d(4),
                                    nn.Flatten(),
                                    nn.Dropout(0.2),
                                    nn.Linear(512, num_classes))
    
  def forward(self, xb):
    out = self.conv1(xb)
    out = self.conv2(out)
    out = self.res1(out) + out

    out = self.conv3(out)
    out = self.conv4(out)
    out = self.res2(out) + out

    return self.classifier(out)

model = to_device(ResNet9(3, 10), device)
print(model)

"""# Training"""

@torch.no_grad()
def evaluate(model, val_loader):
  model.eval()
  outputs = [model.validation_step(batch) for batch in val_loader]
  return model.validation_epoch_end(outputs)

def get_lr(optimizer):
  for param_group in optimizer.param_groups:
    return param_group["lr"]

from tqdm import tqdm

def fit_one_cycle(epochs, max_lr, model, train_loader, val_loader,
                  weight_decay=0, grad_clip=None, opt_func=torch.optim.SGD):
  torch.cuda.empty_cache()
  history = []

  optimizer = opt_func(model.parameters(), max_lr, weight_decay=weight_decay)
  sched = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=max_lr, epochs=epochs, 
                                              steps_per_epoch=len(train_loader))
  
  for epoch in range(epochs):
    # Training Step
    model.train()
    train_losses = []
    lrs = []
    for batch in tqdm(train_loader):
      loss = model.training_step(batch)
      train_losses.append(loss)
      loss.backward()

      # Clip the Gradient
      if grad_clip:
        nn.utils.clip_grad_value_(model.parameters(), grad_clip)

      optimizer.step()
      optimizer.zero_grad()

      # Record and Update the Learning Rate
      lrs.append(get_lr(optimizer))
      sched.step()

    # Validation Step
    result = evaluate(model, val_loader)
    result["train_loss"] = torch.stack(train_losses).mean().item()
    result["lrs"] = lrs
    model.epoch_end(epoch, result)
    history.append(result)
  return history

history = [evaluate(model, val_loader)]
history

epochs = 8
max_lr = 0.01
weight_decay = 1e-5
grad_clip = 0.1
opt_func = torch.optim.Adam

# Commented out IPython magic to ensure Python compatibility.
# %%time
history += fit_one_cycle(epochs, max_lr, model, train_loader, val_loader, 
               weight_decay=weight_decay, grad_clip=grad_clip, opt_func=opt_func)

train_time = "4:6"

def plot_accuracies(history):
  accuracies = [result["val_acc"] for result in history]
  plt.plot(accuracies, "-x")
  plt.xlabel("Epochs")
  plt.ylabel("Accuracies")
  plt.title("Accuracy vs Epoch")

plot_accuracies(history)

def plot_losses(history):
  train_losses = [result.get("train_loss") for result in history]
  val_losses = [result["val_loss"] for result in history]
  plt.plot(train_losses, "-rx")
  plt.plot(val_losses, "-bx")
  plt.xlabel("Epochs")
  plt.ylabel("Loss")
  plt.title("Loss vs Epochs")
  plt.legend(["Training", "Vaalidation"])

plot_losses(history)

def plot_lrs(history):
  lrs = np.concatenate([result.get("lrs", []) for result in history])
  plt.plot(lrs, "-")
  plt.xlabel("Batch No.")
  plt.ylabel("Learning Rate")
  plt.title("Learning Rate vs Batch No.")

plot_lrs(history)

"""# Test Inidividual Image and Evaluate on Test Set"""

test_dataset = ImageFolder(DATA_DIR+"/test", transform=val_tfms)

def predict_image(image, model):
  image = to_device(image.unsqueeze(0), device)
  out = model(image)
  _, preds = torch.max(out, dim=1)
  return preds[0].item()

image, label = test_dataset[1700]
plt.imshow(denormalize(image.unsqueeze(0), *stats).squeeze(0).permute(1, 2, 0))
print("Label: {} Predicted: {}".format(dataset.classes[label], dataset.classes[predict_image(image, model)]))

image, label = test_dataset[17]
plt.imshow(denormalize(image.unsqueeze(0), *stats).squeeze(0).permute(1, 2, 0))
print("Label: {} Predicted: {}".format(dataset.classes[label], dataset.classes[predict_image(image, model)]))

image, label = test_dataset[8000]
plt.imshow(denormalize(image.unsqueeze(0), *stats).squeeze(0).permute(1, 2, 0))
print("Label: {} Predicted: {}".format(dataset.classes[label], dataset.classes[predict_image(image, model)]))

test_loader = DeviceDataLoader(DataLoader(test_dataset, BATCH_SIZE*2), device)
test_result = evaluate(model, test_loader)
test_result

"""# Save Model"""

torch.save(model.state_dict(), "cifar10_resnet9.pth")

model2 = to_device(ResNet9(3, 10), device)
model2.load_state_dict(torch.load("cifar10_resnet9.pth"))

evaluate(model2, test_loader)

# Save the Experiment