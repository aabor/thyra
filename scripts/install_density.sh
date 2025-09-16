#!/usr/bin/env bash
set -e

# python3 -m venv .venv_density
#source .venv_density/bin/activate

#pip install --upgrade pip
# install torch as above (choose proper command from pytorch.org)
#pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Example CSRNet implementation (one of many)
git clone https://github.com/CodeKnight314/Crowd-Counting-Pytorch.git ../thirdparty/csrnet
#cd ../thirdparty/csrnet
#pip install -r requirement.txt || true
# If requirements file is incomplete:
#pip install numpy opencv-python matplotlib pillow

# Download pre-trained model weights per repo instructions (check the repo for links)
# e.g.: cp path/to/weights.pth models/CSRNet.pth

echo "Density model repo cloned at thirdparty/csrnet. Read its README for weights & dataset details."