CUDA_VISIBLE_DEVICES=0,1 python -m torch.distributed.launch --master_port 45955 --nproc_per_node=2 examples/run_myxfun_re.py \
        --overwrite_output_dir \
        --model_name_or_path microsoft/layoutxlm-base \
        --output_dir ./mytmp/test-myremax \
        --evaluation_strategy steps --eval_steps 100 \
        --save_strategy steps --save_steps 100 \
        --load_best_model_at_end \
        --save_total_limit 1 \
        --do_train \
        --do_eval \
        --do_predict \
        --logging_steps 5 \
        --lang zh \
        --max_steps 7500 \
        --per_device_train_batch_size 2 \
        --warmup_ratio 0.1 \
        --fp16