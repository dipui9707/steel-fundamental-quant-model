import subprocess
import json
import os
import time
from datetime import datetime

CANDIDATES = [
    # 1. 铁矿海运费与国际航运
    {"code": "S0176220", "name": "中国进口干散货运价指数:海岬型船:铁矿石:西澳大利亚丹皮尔-青岛", "group": "铁矿海运费"},
    {"code": "S0176221", "name": "中国进口干散货运价指数:海岬型船:铁矿石:巴西图巴朗-青岛", "group": "铁矿海运费"},
    {"code": "S0266069", "name": "中国进口干散货运价指数:海岬型船:铁矿石", "group": "铁矿海运费"},
    {"code": "S0205030", "name": "中国进口干散货运价指数:综合指数", "group": "铁矿海运费"},
    {"code": "S0031550", "name": "波罗的海干散货指数(BDI)", "group": "铁矿海运费"},
    
    # 2. 铁矿核心现货/指数
    {"code": "S0174655", "name": "中国:青岛港:车板价:PB粉矿(61.5%,澳大利亚)", "group": "铁矿现货基准"},
    {"code": "D6279316", "name": "中国:青岛港:市场价:铁矿石:PB粉(进口,61.5%)", "group": "铁矿现货基准"},
    {"code": "A3695347", "name": "中国:迁安:市场价(湿基不含税):铁精粉(0.66)", "group": "铁精粉基准"},
    {"code": "S5716219", "name": "中国:铁矿石价格指数(62%,FOB)", "group": "铁矿价格指数"},

    # 3. 焦煤 (蒙煤口岸/到厂、产地、进口)
    {"code": "U1034836", "name": "蒙古:出厂价:焦煤(5#,甘其毛都口岸)", "group": "蒙煤基准"},
    {"code": "B4120932", "name": "蒙古:出厂价:焦煤(唐山沙河驿产)", "group": "蒙煤基准"},
    {"code": "S5132022", "name": "中国:山西:平均价:主焦煤", "group": "焦煤产地"},
    {"code": "L9524876", "name": "中国:山西:出厂价:焦煤(吕梁产)", "group": "焦煤产地"},
    {"code": "U4421912", "name": "中国:现货领先价格:焦煤", "group": "焦煤领先"},
    {"code": "S5120155", "name": "中国:现货价(到岸价):焦煤(峰景矿,澳大利亚产)", "group": "海运焦煤基准"},
    {"code": "S5132102", "name": "中国:主要港口:平均价:炼焦煤(中国)", "group": "焦煤港口"},
    {"code": "S9982781", "name": "中国:市场均价:炼焦煤", "group": "焦煤全国均价"},

    # 4. 焦炭 (港口平仓准一级、吨焦利润)
    {"code": "S5134898", "name": "中国:日照港:平仓价(含税):冶金焦(准一级,CSR60)", "group": "焦炭港口平仓"},
    {"code": "P8829103", "name": "中国:日照港:市场价:冶金焦(准一级)", "group": "焦炭港口平仓"},
    {"code": "S5132296", "name": "日照港:平均均价:冶金焦(中国产)", "group": "焦炭港口平仓"},
    {"code": "S9985549", "name": "中国:毛利:焦炭", "group": "焦化利润"},

    # 5. 动力煤 (价格联动/蓄水池/电厂需求)
    {"code": "S5104572", "name": "中国:秦皇岛港:平仓价:动力煤(Q5500K)", "group": "动力煤港口价"},
    {"code": "S9983507", "name": "中国:秦皇岛:市场价(含税):动力煤(Q5500)", "group": "动力煤港口价"},
    {"code": "S5133608", "name": "中国:鄂尔多斯:车板价:动力煤(Q5500)", "group": "动力煤产地价"},
    {"code": "S5103725", "name": "中国:秦皇岛港:库存量:煤炭", "group": "动力煤港口库存"},
    {"code": "S5125187", "name": "中国:秦皇岛港:场存量:煤炭", "group": "动力煤港口库存"},
    {"code": "Q0149884", "name": "中国:日耗量:煤炭重点电厂", "group": "动力煤下游日耗"},
    {"code": "V2000618", "name": "中国:库存量:煤炭重点电厂", "group": "动力煤下游库存"},
    {"code": "C2918730", "name": "中国:库存可用天数:煤炭重点电厂", "group": "动力煤下游可用天数"},
    {"code": "S0176223", "name": "中国进口干散货运价指数:海岬型船:煤炭:澳大利亚纽卡斯尔-舟山", "group": "煤炭海运费"},
    {"code": "S0205034", "name": "中国进口干散货运价指数:巴拿马型船:煤炭:印尼萨马林达-广州", "group": "煤炭海运费"},

    # 6. 钢坯与废钢
    {"code": "S0143502", "name": "中国:江苏:价格:方坯(20MnSi)", "group": "钢坯现货"},
    {"code": "S5700017", "name": "中国:唐山:市场价(不含税):废钢(6-8mm)", "group": "废钢现货"},
    {"code": "S5712502", "name": "中国:张家港:市场价(不含税):废钢(6-8mm)", "group": "废钢现货"},
    {"code": "S9973428", "name": "富宝:中国:价格(13%税):重废(三类,≥6mm):沙钢", "group": "沙钢废钢采购价"},
    {"code": "S9973429", "name": "富宝:中国:价格(13%税):高炉废钢(一类):沙钢", "group": "沙钢废钢采购价"},
    {"code": "S9906486", "name": "富宝:中国:日耗量:废钢:147家钢厂", "group": "废钢钢厂日耗"},
    {"code": "S9906513", "name": "富宝:中国:到货量:废钢:109家钢厂", "group": "废钢钢厂到货"}
]

OUT_DIR = "/home/hw/项目/钢材产业系统量化模型/研究/Wind铁矿双焦与动力煤补充探查_20260919"
CLI_PATH = "/home/hw/.agents/skills/wind-mcp-skill/scripts/cli.mjs"

def test_metric(item):
    code = item["code"]
    name = item["name"]
    params = json.dumps({
        "question": code,
        "observation": "2"
    }, ensure_ascii=False)
    cmd = ["node", CLI_PATH, "call", "economic_data", "query_economic_indicator_data", params]
    retrieved_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+0800")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        out_raw = res.stdout.strip()
        try:
            data = json.loads(out_raw)
            wrapped = {
                "request": {
                    "server_type": "economic_data",
                    "tool": "query_economic_indicator_data",
                    "params": {"question": code, "observation": "2"},
                    "target_code": code,
                    "target_name": name
                },
                "retrieved_at": retrieved_at,
                "response": data
            }
            sample_file = os.path.join(OUT_DIR, f"sample_{code}.json")
            with open(sample_file, "w", encoding="utf-8") as f:
                json.dump(wrapped, f, ensure_ascii=False, indent=2)
            
            text_content = ""
            if "content" in data and len(data["content"]) > 0:
                text_content = data["content"][0].get("text", "")
            
            status = "unknown"
            latest_date = None
            latest_value = None
            records_count = 0
            unit = ""
            freq = ""
            source = ""
            meta_name = ""
            
            if "无权限" in text_content or "没有权限" in text_content or "未购买" in text_content or "权限不足" in text_content:
                status = "no_permission"
            elif "没有搜索到指标" in text_content or "未找到相关数据" in text_content:
                status = "not_found"
            else:
                try:
                    inner = json.loads(text_content)
                    if isinstance(inner, dict) and "metrics" in inner and len(inner["metrics"]) > 0:
                        m = inner["metrics"][0]
                        meta = m.get("meta", {})
                        meta_name = meta.get("name", "")
                        unit = meta.get("unit", "")
                        freq = meta.get("freq", "")
                        source = meta.get("source", "")
                        dates = m.get("date", [])
                        values = m.get("value", [])
                        records_count = len(dates)
                        if records_count > 0:
                            latest_date = dates[-1]
                            latest_value = values[-1]
                            status = "accessible"
                        else:
                            status = "empty_series"
                    else:
                        status = "unexpected_format"
                except Exception as ex:
                    status = f"parse_error: {str(ex)}"

            return {
                "code": code,
                "name": name,
                "meta_name": meta_name,
                "group": item["group"],
                "status": status,
                "unit": unit,
                "freq": freq,
                "source": source,
                "latest_date": latest_date,
                "latest_value": latest_value,
                "records_count": records_count,
                "raw_snippet": text_content[:150]
            }
        except Exception as e:
            return {
                "code": code,
                "name": name,
                "group": item["group"],
                "status": "error_json",
                "error": str(e),
                "raw": out_raw[:200]
            }
    except Exception as e:
        return {
            "code": code,
            "name": name,
            "group": item["group"],
            "status": "timeout_or_fail",
            "error": str(e)
        }

if __name__ == "__main__":
    results = []
    print(f"Starting verification of {len(CANDIDATES)} candidates...")
    for idx, item in enumerate(CANDIDATES):
        print(f"[{idx+1}/{len(CANDIDATES)}] Testing {item['code']} - {item['name']}...")
        r = test_metric(item)
        print(f"  Result: {r['status']} | Date: {r.get('latest_date')} | Val: {r.get('latest_value')} | Unit: {r.get('unit')}")
        results.append(r)
        time.sleep(0.3)

    summary_file = os.path.join(OUT_DIR, "候选指标权限实测汇总.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Finished all verifications!")
