git clone https://github.com/facebookresearch/sam2.git && cd sam2

pip install -e .

cd checkpoints && \
./download_ckpts.sh && \
cd ..