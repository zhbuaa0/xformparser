CUDA_VISIBLE_DEVICES=0 python examples/run_myxfun_re.py \
        --overwrite_output_dir \
        --model_name_or_path microsoft/layoutxlm-base \
        --output_dir ./mytmp/haslabel-remaxtest \
        --evaluation_strategy steps --eval_steps 100 \
        --save_strategy steps --save_steps 100 \
        --load_best_model_at_end \
        --save_total_limit 2 \
        --metric_for_best_model f1 \
        --do_train \
        --do_eval \
        --do_predict \
        --logging_steps 5 \
        --lang zh \
        --max_steps 5000 \
        --per_device_train_batch_size 4 \
        --warmup_ratio 0.1 \
        --fp16