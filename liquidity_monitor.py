"""
市场流动性监控面板
===================
核心指标：
  - margin_strength：融资买入额 / 成交额，衡量杠杆资金短期参与度
  - outperform_ratio：跑赢基准指数的股票占比，衡量市场广度

逻辑：
  使用前一日（t-1）融资结构预测当日（t）市场广度，
  避免大市值股票主导：先算个股比率，再做截面平均。
"""

import pandas as pd
from sqlalchemy import create_engine
from pyecharts import options as opts
from pyecharts.charts import Line

# ==========================================
# 配置
# ==========================================
DB_URI = "mysql+pymysql://readonly:REDACTED_PWD@REDACTED_HOST:3306/intern"
STOCK_CODES = ("000858", "300476", "600519", "601991", "688017")
INDEX_CODE = "000300.SH"
START_DATE = "2020-01-01"
END_DATE = "2026-12-31"


# ==========================================
# 1. 数据加载
# ==========================================
def load_stock_data(engine, stock_codes, start_date, end_date):
    """加载个股行情及融资买入数据。

    Returns:
        DataFrame with columns: date, stock_code, pct_chg, rzmre, amt
    """
    codes_str = str(stock_codes)
    query = f"""
        SELECT date, stock_code, pct_chg, rzmre, amt
        FROM stock_daily
        WHERE stock_code IN {codes_str}
          AND date >= '{start_date}'
          AND date <= '{end_date}'
        ORDER BY date, stock_code
    """
    try:
        df = pd.read_sql(query, engine)
    except Exception as e:
        raise RuntimeError(f"个股数据加载失败: {e}")

    df["date"] = pd.to_datetime(df["date"])
    if df.empty:
        raise ValueError("个股数据为空，请检查数据库连接与日期范围。")
    return df


def load_index_data(engine, index_code, start_date, end_date):
    """从 bench_basic_data 加载基准指数日收益率（沪深300）。

    Returns:
        DataFrame with columns: date, index_pct_chg
    """
    query = f"""
        SELECT date, PCT_CHG AS index_pct_chg
        FROM bench_basic_data
        WHERE code = '{index_code}'
          AND date >= '{start_date}'
          AND date <= '{end_date}'
        ORDER BY date
    """
    try:
        df = pd.read_sql(query, engine)
    except Exception as e:
        raise RuntimeError(f"指数数据加载失败: {e}")

    df["date"] = pd.to_datetime(df["date"])
    if df.empty:
        raise ValueError("指数数据为空，请检查数据库连接与指数代码。")
    return df


# ==========================================
# 2. 指标计算
# ==========================================
def calculate_margin_strength(df_stocks):
    """计算杠杆资金参与度 (margin_strength)。

    步骤：
      1. 个股层面：margin_strength_i = rzmre_i / amt_i
      2. 截面平均：mean(margin_strength) by date
      3. 使用前一日融资结构预测当日市场广度：shift(1)

    采用截面平均而非总量比，避免大市值股票主导指标。

    Returns:
        DataFrame with columns: date, margin_strength_shifted
    """
    # 个股比率
    df = df_stocks.copy()
    df["margin_strength"] = df["rzmre"] / df["amt"]

    # 截面均值（等权，避免大市值主导）
    df_daily = df.groupby("date")["margin_strength"].mean().reset_index()
    df_daily.rename(columns={"margin_strength": "margin_strength_raw"}, inplace=True)

    # 使用前一日融资结构预测当日市场广度
    df_daily["margin_strength_shifted"] = df_daily["margin_strength_raw"].shift(1)

    return df_daily[["date", "margin_strength_shifted"]]


def calculate_market_breadth(df_stocks, df_index):
    """计算市场广度：跑赢基准指数的股票占比。

    Returns:
        DataFrame with columns: date, outperform_ratio, pool_size
    """
    merged = pd.merge(df_stocks, df_index, on="date", how="inner")
    merged["is_outperform"] = merged["pct_chg"] > merged["index_pct_chg"]

    daily_count = merged.groupby("date").agg(
        outperform_count=("is_outperform", "sum"),
        pool_size=("is_outperform", "count"),
    ).reset_index()

    daily_count["outperform_ratio"] = (
        daily_count["outperform_count"] / daily_count["pool_size"]
    )

    return daily_count[["date", "outperform_ratio", "pool_size"]]


# ==========================================
# 3. 可视化面板构建
# ==========================================
def build_dashboard(x_data, y_margin, y_breadth):
    """使用 Pyecharts 构建双 Y 轴交互面板。

    Args:
        x_data: 日期字符串列表
        y_margin: 融资参与度 (margin_strength, shifted)
        y_breadth: 市场广度 (outperform_ratio)
    """
    line = (
        Line(init_opts=opts.InitOpts(width="1200px", height="600px", theme="white"))
        .add_xaxis(xaxis_data=x_data)
        # 主 Y 轴：杠杆资金参与度
        .add_yaxis(
            series_name="杠杆资金参与度 (margin_strength)",
            y_axis=y_margin,
            is_smooth=True,
            symbol="emptyCircle",
            symbol_size=6,
            color="#c23531",
            label_opts=opts.LabelOpts(is_show=False),
            yaxis_index=0,
        )
        # 次 Y 轴：市场广度
        .add_yaxis(
            series_name="市场广度 (跑赢基准胜率)",
            y_axis=y_breadth,
            is_smooth=True,
            symbol="circle",
            symbol_size=6,
            color="#2f4554",
            label_opts=opts.LabelOpts(is_show=False),
            yaxis_index=1,
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title="市场流动性监控面板",
                pos_left="center",  pos_top="1%"
            ),
            tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
            legend_opts=opts.LegendOpts(pos_top="5%"),
            datazoom_opts=[
                opts.DataZoomOpts(is_show=True, type_="slider", range_start=30, range_end=100),
            ],
            yaxis_opts=opts.AxisOpts(
                name="融资买入额 / 成交额",
                type_="value",
                position="left",
                axisline_opts=opts.AxisLineOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#c23531")
                ),
            ),
        )
        .extend_axis(
            yaxis=opts.AxisOpts(
                name="相对超额胜率",
                type_="value",
                position="right",
                min_=0.0,
                max_="dataMax",
                axisline_opts=opts.AxisLineOpts(
                    linestyle_opts=opts.LineStyleOpts(color="#2f4554")
                ),
            )
        )
    )

    output_path = "liquidity_dashboard.html"
    line.render(output_path)

    # 注入居中样式
    with open(output_path, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace(
        "</head>",
        "<style>body { display: flex; justify-content: center; }</style></head>",
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


# ==========================================
# 主流程
# ==========================================
def main():
    engine = create_engine(DB_URI)

    print("⏳ 正在从数据库拉取行情与融资买入数据...")

    # 加载数据
    df_stocks = load_stock_data(engine, STOCK_CODES, START_DATE, END_DATE)
    df_index = load_index_data(engine, INDEX_CODE, START_DATE, END_DATE)

    print("🧮 正在计算流动性及市场广度指标...")

    # 计算杠杆资金参与度
    df_margin = calculate_margin_strength(df_stocks)

    # 计算市场广度
    df_breadth = calculate_market_breadth(df_stocks, df_index)

    # 合并面板
    df_panel = pd.merge(df_margin, df_breadth, on="date", how="inner")
    df_panel = df_panel.dropna().sort_values("date")

    print(f"   股票池数量: {df_breadth['pool_size'].iloc[0] if not df_breadth.empty else 'N/A'}")

    # 提取绘图数据
    x_data = df_panel["date"].dt.strftime("%Y-%m-%d").tolist()
    y_margin = df_panel["margin_strength_shifted"].round(4).tolist()
    y_breadth = df_panel["outperform_ratio"].round(2).tolist()

    # 生成面板
    print("🎨 正在生成前端 HTML 交互面板...")
    output_path = build_dashboard(x_data, y_margin, y_breadth)
    print(f"✅ 面板生成成功！请在浏览器中打开：{output_path}")


if __name__ == "__main__":
    main()
