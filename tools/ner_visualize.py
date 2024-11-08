# Lint as: python3
import json
import logging
import os
import cv2
import copy
import numpy as np

from layoutlmft.data.utils import load_image, merge_bbox, normalize_bbox, simplify_bbox
from transformers import AutoTokenizer

_LANG = ["zh", "de", "es", "fr", "en", "it", "ja", "pt"]
logger = logging.getLogger(__name__)
test_name = "mytrain"
tokenizer = AutoTokenizer.from_pretrained("xlm-roberta-base")


def _generate_examples(preds_path, filepaths,output_path):

    items = []
    for filepath in filepaths:
        logger.info("Generating examples from = %s", filepath)
        with open(filepath[0], "r") as f:
            data = json.load(f)

        for doc in data["documents"]:
            doc["img"]["fpath"] = os.path.join(filepath[1], doc["img"]["fname"])
            image, size = load_image(doc["img"]["fpath"])
            document = doc["document"]
            tokenized_doc = {"input_ids": [], "bbox": [], "labels": [], "bbox_src": []}
            entities = []
            relations = []
            id2label = {}
            offsets = []
            lines = []
            entity_id_to_index_map = {}
            empty_entity = set()
            for line in document:
                if len(line["text"]) == 0:
                    empty_entity.add(line["id"])
                    continue
                id2label[line["id"]] = line["label"]
                relations.extend([tuple(sorted(l)) for l in line["linking"]])
                tokenized_inputs = tokenizer(
                    line["text"],
                    add_special_tokens=False,
                    return_offsets_mapping=True,
                    return_attention_mask=False,
                )

                lines.append(line['text'])
                offsets.append(tokenized_inputs['offset_mapping'])

                text_length = 0
                ocr_length = 0
                bbox = []
                bbox_src = []
                last_box = None
                for token_id, offset in zip(tokenized_inputs["input_ids"], tokenized_inputs["offset_mapping"]):
                    if token_id == 6:
                        bbox.append(None)
                        bbox_src.append(None)
                        continue
                    text_length += offset[1] - offset[0]
                    tmp_box = []
                    # while ocr_length < text_length:
                    #     ocr_word = line["words"].pop(0)
                    #     ocr_length += len(
                    #         tokenizer._tokenizer.normalizer.normalize_str(ocr_word["text"].strip())
                    #     )
                    #     tmp_box.append(simplify_bbox(ocr_word["box"]))
                    # if len(tmp_box) == 0:
                    #     tmp_box = last_box
                    # bbox.append(normalize_bbox(merge_bbox(tmp_box), size))
                    # bbox_src.append(merge_bbox(tmp_box))
                    # last_box = tmp_box
                    bbox_src.append(simplify_bbox(line['box']))
                    bbox.append(simplify_bbox(line['box']))
                # print(line['box'])
                bbox = [
                    [bbox[i + 1][0], bbox[i + 1][1], bbox[i + 1][1], bbox[i + 1][2]] if b is None else b
                    for i, b in enumerate(bbox)
                ]
                bbox_src = [
                    [bbox_src[i + 1][0], bbox_src[i + 1][1], bbox_src[i + 1][1], bbox_src[i + 1][2]] if b is None else b
                    for i, b in enumerate(bbox_src)
                ]
                if line["label"] == "other":
                    label = ["O"] * len(bbox)
                else:
                    label = [f"I-{line['label'].upper()}"] * len(bbox)
                    label[0] = f"B-{line['label'].upper()}"
                tokenized_inputs.update({"bbox": bbox, "labels": label, "bbox_src": bbox_src})
                # if label[0] != "O":
                    # entity_id_to_index_map:每个实体对应一个唯一id，为每个id按照顺序重新索引
                entity_id_to_index_map[line["id"]] = len(entities)
                entities.append(
                    {
                        "start": len(tokenized_doc["input_ids"]),
                        "end": len(tokenized_doc["input_ids"]) + len(tokenized_inputs["input_ids"]),
                        "label": line["label"].upper(),
                    }
                )
                for i in tokenized_doc:
                    tokenized_doc[i] = tokenized_doc[i] + tokenized_inputs[i]
            relations = list(set(relations))
            relations = [rel for rel in relations if rel[0] not in empty_entity and rel[1] not in empty_entity]
            kvrelations = []
            for rel in relations:
                pair = [id2label[rel[0]], id2label[rel[1]]]
                if pair == ["question", "answer"]:
                    kvrelations.append(
                        {"head": entity_id_to_index_map[rel[0]], "tail": entity_id_to_index_map[rel[1]]}
                    )
                elif pair == ["answer", "question"]:
                    kvrelations.append(
                        {"head": entity_id_to_index_map[rel[1]], "tail": entity_id_to_index_map[rel[0]]}
                    )
                else:
                    continue

            def get_relation_span(rel):
                bound = []
                for entity_index in [rel["head"], rel["tail"]]:
                    bound.append(entities[entity_index]["start"])
                    bound.append(entities[entity_index]["end"])
                return min(bound), max(bound)

            relations = sorted(
                [
                    {
                        "head": rel["head"],
                        "tail": rel["tail"],
                        "start_index": get_relation_span(rel)[0],
                        "end_index": get_relation_span(rel)[1],
                    }
                    for rel in kvrelations
                ],
                key=lambda x: x["head"],
            )
            chunk_size = 512
            for chunk_id, index in enumerate(range(0, len(tokenized_doc["input_ids"]), chunk_size)):
                item = {}
                for k in tokenized_doc:
                    item[k] = tokenized_doc[k][index: index + chunk_size]
                # entities_in_this_span保存切分后的所有实体
                entities_in_this_span = []
                # global_to_this_span 为切分的实体id-->切分后的实体id
                global_to_local_map = {}
                for entity_id, entity in enumerate(entities):
                    if (
                            index <= entity["start"] < index + chunk_size
                            and index <= entity["end"] < index + chunk_size
                    ):
                        entity["start"] = entity["start"] - index
                        entity["end"] = entity["end"] - index
                        global_to_local_map[entity_id] = len(entities_in_this_span)
                        entities_in_this_span.append(entity)
                relations_in_this_span = []
                for relation in relations:
                    # relation_span: start_index前实体的start，end_index尾实体的end
                    if (
                            index <= relation["start_index"] < index + chunk_size
                            and index <= relation["end_index"] < index + chunk_size
                    ):
                        relations_in_this_span.append(
                            {
                                "head": global_to_local_map[relation["head"]],  # 切分后的头实体的索引
                                "tail": global_to_local_map[relation["tail"]],  # 切分后的尾实体的索引
                                "start_index": relation["start_index"] - index,
                                "end_index": relation["end_index"] - index,
                            }
                        )
                item.update(
                    {
                        "id": f"{doc['id']}_{chunk_id}",
                        "image": "image",
                        "entities": entities_in_this_span,
                        "relations": relations_in_this_span,
                        'offsets': offsets,
                        'lines': lines,
                    }
                )
                items.append(item)
    with open('/home/zhanghang-s21/data/bishe/data/token_%s.json'% test_name, mode='w') as f:
        json.dump(items, f, indent=2)
    with open(preds_path, 'r') as f:
        preds = []
        for line in f.readlines():
            preds.append(line.split())
    assert len(preds) == len(items)

    docs = {}
    for i, item in enumerate(items):
        item['pred'] = preds[i]
        if test_name == "mytrain":
            tp, _ = item['id'].split('.')
            _, uid = tp.split('_')
        else:
            _, _, uid, chu = item['id'].split('_')
        if uid in docs:
            docs[uid] += [item]
        else:
            docs[uid] = [item]
            
    with open('/home/zhanghang-s21/data/bishe/result/ner_%s_result.json'%test_name, mode='w') as f:
        json.dump(docs, f, indent=2)
    
    for doc_id, doc in docs.items():
        bbox_src = []
        pred = []
        lines = []
        labels = []
        for d in doc:
            bbox_src.extend(d['bbox_src'])
            pred.extend(d['pred'])
            labels.extend(d['labels'])
            if lines == []:
                lines.extend(d['lines'])
        line = ' '.join(lines)
        tokenizer_output = tokenizer(
            line,
            add_special_tokens=False,
            return_offsets_mapping=True,
            return_attention_mask=False,
        )

        tokens = tokenizer.tokenize(line)
        offset = tokenizer_output['offset_mapping']

        assert len(offset) == len(bbox_src) == len(pred) == len(tokens) == len(labels)
        
        img_path = os.path.join(filepaths[0][1], 'zh_%s_%s' % (test_name, doc_id))
        save_path = os.path.join(output_path, 'zh_show_%s_%s' % (test_name, doc_id))
        if not os.path.exists(os.path.dirname(save_path)):
            os.makedirs(os.path.dirname(save_path))
        img = cv2.imread(img_path)
        
        print(img_path)
        print(save_path)
        def get_rec(doc_id, data, results, tokens):
            end = -1
            for doc in data["documents"]:
                now_id = doc['id']
                if now_id[-1*len(doc_id):] == doc_id:
                    break
            
            for index, p in enumerate(results):
                if index < end:
                    continue
                if p == 'O':
                    continue
                else:
                    tag = p.split('-')[-1]
                    end = index + 1
                    while end < len(results) and results[end] == 'I-' + tag:
                        end += 1

                    ent_bbox = bbox_src[index:end]
                    x1, y1, x2, y2 = [], [], [], []
                    for bb in ent_bbox:
                        x1.append(bb[0])
                        y1.append(bb[1])
                        x2.append(bb[2])
                        y2.append(bb[3])
                    x1 = int(min(x1))
                    y1 = int(min(y1))
                    x2 = int(max(x2))
                    y2 = int(max(y2))
                    # print(img.shape)
                    # print(x1,y1,x2,y2)
                    if tag == 'QUESTION':
                        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 1)
                    elif tag == 'ANSWER':
                        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 1)
                    else:
                        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 0), 1)
            return img
        def draw_rec(img, results, tokens):
            end = -1
            for index, p in enumerate(results):
                if index < end:
                    continue
                if p == 'O':
                    continue
                else:
                    tag = p.split('-')[-1]
                    end = index + 1
                    while end < len(results) and results[end] == 'I-' + tag:
                        end += 1

                    ent_bbox = bbox_src[index:end]
                    x1, y1, x2, y2 = [], [], [], []
                    for bb in ent_bbox:
                        x1.append(bb[0])
                        y1.append(bb[1])
                        x2.append(bb[2])
                        y2.append(bb[3])
                    x1 = int(min(x1))
                    y1 = int(min(y1))
                    x2 = int(max(x2))
                    y2 = int(max(y2))
                    # print(img.shape)
                    # print(x1,y1,x2,y2)
                    if tag == 'QUESTION':
                        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 1)
                    elif tag == 'ANSWER':
                        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 1)
                    else:
                        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 0), 1)
            return img

        def function(image1, image2):
            h1, w1, c1 = image1.shape
            h2, w2, c2 = image2.shape
            if c1 != c2:
                print("channels NOT match, cannot merge")
                return
            else:
                image3 = np.hstack([image1, image2])

            return image3

        img_pred = draw_rec(copy.deepcopy(img), pred, tokens)
        img_label = draw_rec(copy.deepcopy(img), labels, tokens)
        cv2.imwrite(save_path,img_pred)
        # cv2.imwrite(save_path, function(img_label, img_pred))

        # with open('test.txt', 'w') as f:
        #     for t, l in zip(tokens, labels):
        #         f.write(t + '\t' + l + '\n')


if __name__ == '__main__':
    '''
    将实体的识别结果跟真是结果显示在图片中
    '''
    # /home/zhanghang-s21/data/layoutlmft/tmp/test-myner/validation_data_test_predictions.txt
    preds_path = '/home/zhanghang-s21/data/layoutlmft/tmp/test-myner/'+ test_name +'_data_test_predictions.txt'
    preds_path = '/home/zhanghang-s21/data/layoutlmft/tmp/test-myner/test_data_test_predictions2.txt'
    # filepaths = [['/home/zhanghang-s21/data/bishe/MYXFUND/zh.my'+test_name+'.json',
    #               '/home/zhanghang-s21/data/bishe/MYXFUND/zh.'+test_name]]
    filepaths = [["/home/zhanghang-s21/data/bishe/nowdataset/"+test_name+'.json',
                  "/home/zhanghang-s21/data/bishe/nowdataset/"+test_name]]
    output_path = '/home/zhanghang-s21/data/bishe/MYXFUND/ner_visualize'
    
    _generate_examples(preds_path, filepaths, output_path)
