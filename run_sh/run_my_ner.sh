CUDA_VISIBLE_DEVICES=1,3 python -m torch.distributed.launch --master_port 45662 --nproc_per_node=2 examples/run_myxfun_ser.py \
        --model_name_or_path microsoft/layoutxlm-base \
        --overwrite_output_dir \
        --output_dir ./mytmp/test-myner \
        --evaluation_strategy steps --eval_steps 100 \
        --save_strategy steps --save_steps 100 \
        --load_best_model_at_end \
        --save_total_limit 1 \
        --logging_steps 5 \
        --per_device_eval_batch_size 1 \
        --do_train \
        --do_eval \
        --do_predict \
        --lang zh \
        --max_steps 2000 \
        --warmup_ratio 0.1 \
        --fp16