"""Download explicitly during installation, never during request processing."""
import argparse
import os
from pathlib import Path
root=Path(__file__).resolve().parent.parent
os.environ.setdefault('HF_HOME',str(root/'data'/'hf-cache'))
from huggingface_hub import snapshot_download
p=argparse.ArgumentParser()
p.add_argument('--model',default='small',choices=['tiny','base','small','medium','large-v3'])
a=p.parse_args()
target=Path(__file__).resolve().parent.parent/'backend'/'models'/a.model
snapshot_download('Systran/faster-whisper-'+a.model,local_dir=target,
                  allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.*','preprocessor_config.json'])
print('Installed model:',target)
