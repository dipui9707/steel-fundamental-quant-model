#!/usr/bin/env python3
"""
更新 A03 数据地图与 A09 研究假设库
1. 在 A03 登记期货全合约 Parquet 资产与新增期货衍生指标
2. 在 A09 登记 ARCH-H-017 (跨期月间价差与库存传导) 与 ARCH-H-018 (盘面虚拟毛利与负反馈边界)
"""

from pathlib import Path
import openpyxl

BASE_DIR = Path(__file__).resolve().parent.parent
A03_PATH = BASE_DIR / "outputs" / "阶段A_框架初版" / "A03_数据地图.xlsx"
A09_PATH = BASE_DIR / "outputs" / "阶段A_框架初版" / "A09_研究假设库.xlsx"

# A03 新增变量列表 (17项)
# 列: ['变量ID', '模块', '变量名称', '经济含义', '数据频率', '数据来源', '单位', '是否可获得', '是否必须', '代理变量', '原始或计算', 'data_date', 'available_date', '来源代码', '统计样本与口径', '历史起点', '发布时间与过期规则', '备注']
NEW_A03_VARS = [
    [
        "FUT_ALL_PARQUET", "期货行情", "黑色五品种全合约日线Parquet仓库",
        "螺纹/热卷/铁矿/焦炭/焦煤历史全月份实约、主力与指数日线数据",
        "日频", "SHFE/DCE官方及全量日线包", "元/吨/手", "可获得", "必须", "否", "原始",
        None, None, "FUT_PARQUET_2016_2026", "上期所/大商所全量84-87个合约", "2016-01-05", "每日15:30收盘", "全合约开高低收量仓及结算价120,826行"
    ],
    [
        "SPREAD_FUT_HC_RB", "跨品种价差", "华东盘面卷螺差",
        "热轧卷板主力收盘减螺纹钢主力收盘价，反映板长需求强弱分化与钢厂铁水转炉分流倾向",
        "日频", "SHFE", "元/吨", "可获得", "必须", "否", "计算",
        None, None, "HC_MAIN_CLOSE - RB_MAIN_CLOSE", "连续主力合约每日收盘价差", "2016-01-05", "每日15:30", "正值代表板材强于长材"
    ],
    [
        "RATIO_RB_I", "跨品种比价", "螺矿比",
        "螺纹钢主力收盘价与铁矿石主力收盘价比值，反映吨钢对主要原料的估值相对强弱",
        "日频", "SHFE/DCE", "比值", "可获得", "可选", "否", "计算",
        None, None, "RB_MAIN / I_MAIN", "主力收盘价之比", "2016-01-05", "每日15:30", "比值上升代表成材利润扩张或铁矿估值承压"
    ],
    [
        "RATIO_J_I", "跨品种比价", "焦矿比",
        "焦炭主力收盘价与铁矿石主力收盘价比值，反映炉料内部两强相对强弱与入炉配比约束",
        "日频", "DCE", "比值", "可获得", "可选", "否", "计算",
        None, None, "J_MAIN / I_MAIN", "主力收盘价之比", "2016-01-05", "每日15:30", "反映双焦与铁矿的估值天平"
    ],
    [
        "VIRTUAL_STEEL_MARGIN", "钢厂利润", "盘面虚拟钢厂毛利",
        "吨钢盘面虚拟毛利=RB-1.6*I-0.5*J，衡量长流程即期盘面锁定毛利与复产减产边界",
        "日频", "SHFE/DCE", "元/吨", "可获得", "必须", "否", "计算",
        None, None, "RB - 1.6*I - 0.5*J", "经典标准配比盘面虚拟毛利", "2016-01-05", "每日15:30", "击穿现金成本易触发自主减产负反馈"
    ],
    [
        "CAPITAL_RB", "资金持仓", "螺纹钢全市场沉淀资金",
        "螺纹全市场所有存续合约总持仓资金沉淀=OI*结算价*10*8%",
        "日频", "SHFE", "亿元", "可获得", "必须", "否", "计算",
        None, None, "RB_INDEX_OI * SETTLEMENT * 10 * 8%", "全市场所有合约沉淀保证金规模", "2016-01-05", "每日15:30", "真实反映螺纹品种的资金参与深度"
    ],
    [
        "CAPITAL_HC", "资金持仓", "热轧卷板全市场沉淀资金",
        "热卷全市场所有存续合约总持仓资金沉淀=OI*结算价*10*8%",
        "日频", "SHFE", "亿元", "可获得", "可选", "否", "计算",
        None, None, "HC_INDEX_OI * SETTLEMENT * 10 * 8%", "全市场所有合约沉淀保证金规模", "2016-01-05", "每日15:30", "反映热卷品种资金沉淀规模"
    ],
    [
        "CAPITAL_I", "资金持仓", "铁矿石全市场沉淀资金",
        "铁矿石全市场所有存续合约总持仓资金沉淀=OI*结算价*100*12%",
        "日频", "DCE", "亿元", "可获得", "可选", "否", "计算",
        None, None, "I_INDEX_OI * SETTLEMENT * 100 * 12%", "全市场所有合约沉淀保证金规模", "2016-01-05", "每日15:30", "反映铁矿石品种资金沉淀规模"
    ],
    [
        "CAPITAL_J", "资金持仓", "焦炭全市场沉淀资金",
        "焦炭全市场所有存续合约总持仓资金沉淀=OI*结算价*100*15%",
        "日频", "DCE", "亿元", "可获得", "可选", "否", "计算",
        None, None, "J_INDEX_OI * SETTLEMENT * 100 * 15%", "全市场所有合约沉淀保证金规模", "2016-01-05", "每日15:30", "反映焦炭品种资金沉淀规模"
    ],
    [
        "CAPITAL_JM", "资金持仓", "焦煤全市场沉淀资金",
        "焦煤全市场所有存续合约总持仓资金沉淀=OI*结算价*60*15%",
        "日频", "DCE", "亿元", "可获得", "可选", "否", "计算",
        None, None, "JM_INDEX_OI * SETTLEMENT * 60 * 15%", "全市场所有合约沉淀保证金规模", "2016-01-05", "每日15:30", "反映焦煤品种资金沉淀规模"
    ],
    [
        "RB_SPREAD_TOP2", "期限结构", "螺纹主力次主力跨期价差",
        "螺纹前两大持仓合约近月价格减远月价格，衡量近期与远期供需预期差与期限结构升贴水",
        "日频", "SHFE", "元/吨", "可获得", "必须", "否", "计算",
        None, None, "RB_NEAR_CLOSE - RB_FAR_CLOSE", "持仓量前两大主力近远月价差", "2019-10-16", "每日15:30", "正值反向市场Backwardation,负值正向Contango"
    ],
    [
        "RB_ROLL_YIELD_ANNUAL", "期限结构", "螺纹活跃跨期年化展期收益率",
        "近远月价差相对远月价格的年化百分比，用于精确刻画基差斜率与持有收益率",
        "日频", "SHFE", "%", "可获得", "必须", "否", "计算",
        None, None, "((Near - Far) / Far) * (12 / MonthDiff) * 100", "活跃合约年化展期收益率", "2019-10-16", "每日15:30", "升贴水曲率的核心量化代理"
    ],
    [
        "BASIS_ZHONGTIAN_MAIN", "现货基差", "杭州中天现货主力基差",
        "杭州中天螺纹现货价格减去主力期货收盘价，反映期现主流流动性贸易定价基准",
        "日频", "自录/SHFE", "元/吨", "可获得", "必须", "否", "计算",
        None, None, "spot_hz_zhongtian - rb_main_close", "杭州中天现货对主力基差", "2016-01-05", "每日15:30", "含60-90元品牌溢价锚"
    ],
    [
        "BASIS_TIER3_MAIN", "现货基差", "杭州三类现货主力基差",
        "杭州三类螺纹现货价格减去主力期货收盘价，反映CTD最便宜交割品对主力合约基差",
        "日频", "自录/SHFE", "元/吨", "可获得", "必须", "否", "计算",
        None, None, "spot_hz_tier3 - rb_main_close", "杭州三类交割品对主力基差", "2016-01-05", "每日15:30", "CTD基差交割日前夕趋向收敛"
    ],
    [
        "DAYS_TO_DELIVERY", "期现套利", "螺纹主力交割剩余自然日",
        "主力合约距每月15日交割日的实际自然天数，用于资金利息时间衰减折算",
        "日频", "SHFE", "天", "可获得", "必须", "否", "计算",
        None, None, "delivery_date - current_date", "距交割日剩余天数", "2016-01-05", "每日15:30", "时间价值衰减核心参数"
    ],
    [
        "CARRY_TOTAL_COST", "期现套利", "螺纹纯资金利息持仓成本",
        "CTD现货*6%*(剩余天数/365)，用户明确约定仅计算资金利息，不计仓储与其他杂费",
        "日频", "自录/SHFE", "元/吨", "可获得", "必须", "否", "计算",
        None, None, "spot_hz_tier3 * 0.06 * (DAYS / 365)", "纯6%年化资金成本", "2016-01-05", "每日15:30", "期现正套必须扣除的资金门槛"
    ],
    [
        "NET_CASH_CARRY_MARGIN", "期现套利", "螺纹期现正套净利润",
        "主力期货收盘价 - CTD三类现货 - 纯资金利息成本，衡量无风险正套理论净利润空间",
        "日频", "自录/SHFE", "元/吨", "可获得", "必须", "否", "计算",
        None, None, "rb_close - spot_hz_tier3 - CARRY_TOTAL_COST", "无风险正套净利润", "2016-01-05", "每日15:30", ">0时吸引套利盘进场抛空锁润驱动基差收敛"
    ]
]


# A09 新增研究假设 (2项)
# 列: ['Hypothesis ID', '提出日期', '假设内容', '来源行情或文档', '经济逻辑', '需要的数据', '可证伪条件', '历史样本范围', '历史验证结果', '样本外范围', '样本外验证结果', '状态', '是否进入正式模型', '模型版本', '关联复盘ID', '证据路径', '下一步']
NEW_A09_HYPOTHESES = [
    [
        "ARCH-H-017",
        "2026-09-20",
        "黑色量化团队/Antigravity",
        "期限结构与库存蓄水池传导机制",
        "螺纹跨期月间价差(Calendar Spreads 01-05/05-10/10-01)与现货库存蓄水池相互印证假说",
        "跨期月间价差直接反映近端供需现实与远端预期的强弱对比。当现货累库、出库低迷、库销比高企时，近月承压贴水远月呈正向市场(Contango，价差<0)，促使套利商在近月买入仓单并抛空远月锁定无风险利差，反过来加剧近月抛盘；当供需缺货、低库存且出库旺盛时，近月升水远月呈反向市场(Backwardation，价差>0)，反映现货逼仓并加速去库驱动。价差曲线反转往往领先库存拐点1-2周。",
        "期限结构/库存传导/跨期套利",
        "RB_SPREAD_TOP2, RB_ROLL_YIELD_ANNUAL, HZ_DAYS_TO_CLEAR, inv_hz_stock, flow_hz_outflow",
        "全合约日线Parquet (2019-2026) 与杭州现货日度库销比历史序列",
        "2019-2025 历史月间价差与库存拐点相关性 > 0.65",
        "2026年样本外验证中",
        "待验证",
        "候选",
        "否",
        "阶段A候选假设",
        None,
        "数据/原始/期货合约全量日线/standardized/rb_daily.parquet",
        "构建月间价差时序与库存高低拐点的多周期先导性滞后互相关检验"
    ],
    [
        "ARCH-H-018",
        "2026-09-20",
        "黑色量化团队/Antigravity",
        "产业因果/成本负反馈",
        "盘面虚拟钢厂毛利(VIRTUAL_STEEL_MARGIN)对铁水产量与原料负反馈的非线性边界假说",
        "盘面虚拟钢厂毛利=RB-1.6*I-0.5*J，是长流程钢厂在盘面提前锁定生产利润的直接风向标。当虚拟毛利大于200元/吨时，高炉复产动力充沛，带动铁矿双焦补库，形成'成材带原料'的正反馈；当虚拟毛利击穿现金成本甚至深度亏损(<-100元/吨)并持续2周以上时，长流程钢厂亏损倒逼自主检修减产，铁水产量见顶回落，引发原料端(尤其是高估值铁矿)踩踏式补跌，形成'成材倒逼原料负反馈'。负反馈彻底释放后方可筑底。",
        "钢厂利润/铁水产量/原料负反馈",
        "VIRTUAL_STEEL_MARGIN, SPREAD_FUT_HC_RB, RATIO_RB_I, cost_east_hot_metal",
        "连续主力全合约行情 (2016-2026) 与富宝铁水成本/全国日均铁水产量",
        "2016-2025 历次长流程深度亏损期(如2018Q4、2022年中、2024Q1)毛利触底与原料负反馈幅度验证",
        "2026年样本外验证中",
        "待验证",
        "候选",
        "否",
        "阶段A候选假设",
        None,
        "数据/加工/加工指标.csv 中的 VIRTUAL_STEEL_MARGIN 序列",
        "在阶段A回测推演中加入盘面毛利穿透铁水产量与原料暴跌的时滞统计"
    ]
]


def update_a03():
    print(f"Loading A03 workbook from {A03_PATH}...")
    wb = openpyxl.load_workbook(A03_PATH)
    ws = wb["变量登记"]
    
    start_row = 213
    for i, row_data in enumerate(NEW_A03_VARS):
        cur_row = start_row + i
        for c, val in enumerate(row_data, start=1):
            ws.cell(cur_row, c).value = val
            
    new_max_row = start_row + len(NEW_A03_VARS) - 1
    # 扩展 Table Register1
    for tbl in ws.tables.values():
        if tbl.name == "Register1":
            tbl.ref = f"A5:R{new_max_row}"
            print(f"Updated Table Register1 ref to A5:R{new_max_row}")
            
    wb.save(A03_PATH)
    print(f"Successfully updated A03. Total variables registered: {new_max_row - 5 + 1} (Row 5 to {new_max_row})")


def update_a09():
    print(f"Loading A09 workbook from {A09_PATH}...")
    wb = openpyxl.load_workbook(A09_PATH)
    ws = wb["假设登记"]
    
    start_row = 25
    for i, row_data in enumerate(NEW_A09_HYPOTHESES):
        cur_row = start_row + i
        for c, val in enumerate(row_data, start=1):
            ws.cell(cur_row, c).value = val
            
    new_max_row = start_row + len(NEW_A09_HYPOTHESES) - 1
    # 扩展 Table Register4
    for tbl in ws.tables.values():
        if tbl.name == "Register4":
            tbl.ref = f"A5:Q{new_max_row}"
            print(f"Updated Table Register4 ref to A5:Q{new_max_row}")
            
    wb.save(A09_PATH)
    print(f"Successfully updated A09. Total hypotheses registered: {new_max_row - 5 + 1} (Row 5 to {new_max_row})")


if __name__ == "__main__":
    update_a03()
    update_a09()
