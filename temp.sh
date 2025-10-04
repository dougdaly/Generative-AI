# 0) Fresh env deps (keep your current versions if already OK)
pip install -U "diffusers>=0.35" transformers accelerate peft safetensors datasets Pillow

# 1) Grab the official examples (keeps you on the supported path)
git clone https://github.com/huggingface/diffusers.git
cd diffusers
pip install -e .   # editable install so examples match library version

# 2) Prepare data
# Folder with pairs: image.{jpg|png|webp} + image.txt (caption lines).
# Include your TI placeholder in captions, e.g.:
#   data/pokemon_lora/pikachu_0001.png
#   data/pokemon_lora/pikachu_0001.txt  (content: "<pk_pikachu>, pikachu pokemon, 3d render")

# 3) Configure Accelerate
accelerate config default

# 4) Train LoRA (UNet-only; SD 1.5). Adjust steps/batch to your machine.
accelerate launch examples/text_to_image/train_text_to_image_lora.py \
  --pretrained_model_name_or_path runwayml/stable-diffusion-v1-5 \
  --resolution 512 \
  --train_data_dir "/Users/douglasdaly/Documents/Github/Generative-AI/datasets/pokemon-images/pikachu/images" \
  --train_batch_size 2 \
  --gradient_accumulation_steps 4 \
  --learning_rate 1e-4 \
  --lr_scheduler cosine --lr_warmup_steps 100 \
  --max_train_steps 800 \
  --checkpointing_steps 200 \
  --seed 42 \
  --output_dir "./results/lora_diffusers_native"

