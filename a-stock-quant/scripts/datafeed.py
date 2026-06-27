"""数据访问层：带本地缓存 + 多源失败转移。
- L0 历史底仓: baostock (免费免token, 最稳) -> parquet 缓存
- L1 盘后增强: akshare (行业资金流/涨停池/人气榜/概念)
- L2 准实时: adata -> efinance -> akshare 兜底
所有数据落地 data/ 目录 (parquet)，增量更新。
"""
from __future__ import annotations
import os, time, datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
HIST = DATA / "hist"; HIST.mkdir(exist_ok=True)
CACHE = DATA / "cache"; CACHE.mkdir(exist_ok=True)


def _today() -> str:
    return dt.date.today().strftime("%Y%m%d")


# ---------- baostock 会话管理 ----------
class _BS:
    _logged = False

    @classmethod
    def ensure(cls):
        import baostock as bs
        if not cls._logged:
            lg = bs.login()
            if lg.error_code != "0":
                raise RuntimeError(f"baostock login failed: {lg.error_msg}")
            cls._logged = True
        return bs

    @classmethod
    def close(cls):
        if cls._logged:
            import baostock as bs
            bs.logout(); cls._logged = False


# 常用指数 -> baostock 代码 (指数前缀与个股不同, 必须显式映射)
_INDEX_MAP = {
    "000300": "sh.000300",  # 沪深300
    "000985": "sh.000985",  # 中证全指
    "000905": "sh.000905",  # 中证500
    "000016": "sh.000016",  # 上证50
    "399006": "sz.399006",  # 创业板指
    "000001": "sh.000001",  # 上证指数 (注意与平安银行 sz.000001 冲突, 指数优先用映射)
}


def _bs_code(code: str, is_index: bool = False) -> str:
    """个股: 600519->sh.600519, 000001->sz.000001, 300xxx->sz.300xxx, 688xxx->sh.688xxx
    指数: 通过 _INDEX_MAP 显式映射 (沪深300=sh.000300)。"""
    code = str(code).strip().split(".")[0]
    if is_index or code in _INDEX_MAP:
        return _INDEX_MAP.get(code, f"sh.{code}")
    if code.startswith(("60", "68", "9")):
        return f"sh.{code}"
    if code.startswith(("00", "30", "20")):
        return f"sz.{code}"
    if code.startswith(("4", "8")):
        return f"bj.{code}"
    return f"sh.{code}"


def get_hist(code: str, start: str, end: str | None = None, adjust: str = "2") -> pd.DataFrame:
    """单只历史日线 (前复权 adjust=2). 带 parquet 缓存。
    返回列: date open high low close volume amount, index=date(datetime)。"""
    end = end or dt.date.today().strftime("%Y-%m-%d")
    bscode = _bs_code(code)
    fp = HIST / f"{bscode.replace('.', '_')}.parquet"
    cached = None
    if fp.exists():
        cached = pd.read_parquet(fp)
        if not isinstance(cached.index, pd.DatetimeIndex):
            if "date" in cached.columns:
                cached["date"] = pd.to_datetime(cached["date"])
                cached = cached.set_index("date")
            else:
                cached.index = pd.to_datetime(cached.index)
        cached = cached.sort_index()
    # 若缓存已覆盖到 end，直接切片返回
    if cached is not None and not cached.empty and str(cached.index.max().date()) >= end:
        return cached.loc[start:end].copy()
    bs = _BS.ensure()
    fetch_start = start
    if cached is not None and not cached.empty:
        fetch_start = (cached.index.max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    rs = bs.query_history_k_data_plus(
        bscode, "date,open,high,low,close,volume,amount",
        start_date=fetch_start, end_date=end, frequency="d", adjustflag=adjust)
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if rows:
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
        for c in ["open", "high", "low", "close", "volume", "amount"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        if cached is not None and not cached.empty:
            df = pd.concat([cached, df])
            df = df[~df.index.duplicated(keep="last")].sort_index()
        df.to_parquet(fp)
        cached = df
    if cached is None:
        return pd.DataFrame()
    return cached.loc[start:end].copy()


def get_index_hist(index_code: str, start: str, end: str | None = None) -> pd.DataFrame:
    """指数日线 (中证全指 000985 / 沪深300 000300). 指数用 adjustflag=3(不复权)。"""
    end = end or dt.date.today().strftime("%Y-%m-%d")
    return get_hist(index_code, start, end, adjust="3")


# ---------- akshare 盘后增强 (带当日缓存) ----------
def _cache_get(name: str, ttl_sec: int = 3600):
    fp = CACHE / f"{name}_{_today()}.parquet"
    if fp.exists() and (time.time() - fp.stat().st_mtime) < ttl_sec:
        return pd.read_parquet(fp)
    return None


def _cache_put(name: str, df: pd.DataFrame):
    fp = CACHE / f"{name}_{_today()}.parquet"
    try:
        df.to_parquet(fp)
    except Exception:
        pass


def sector_fund_flow(indicator: str = "今日", sector_type: str = "行业资金流") -> pd.DataFrame:
    """行业/概念资金流排名 (akshare)。indicator: 今日/5日/10日。"""
    name = f"sff_{sector_type}_{indicator}"
    c = _cache_get(name, ttl_sec=1800)
    if c is not None:
        return c
    import akshare as ak
    df = ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type=sector_type)
    _cache_put(name, df)
    return df


def zt_pool(date: str | None = None) -> pd.DataFrame:
    """涨停股池 (akshare)。"""
    date = date or _today()
    name = f"zt_{date}"
    c = _cache_get(name, ttl_sec=6 * 3600)
    if c is not None:
        return c
    import akshare as ak
    df = ak.stock_zt_pool_em(date=date)
    _cache_put(name, df)
    return df


def hot_rank() -> pd.DataFrame:
    """A股人气榜 (akshare 东财)。"""
    c = _cache_get("hotrank", ttl_sec=1800)
    if c is not None:
        return c
    import akshare as ak
    df = ak.stock_hot_rank_em()
    _cache_put("hotrank", df)
    return df


def industry_members(industry_name: str) -> pd.DataFrame:
    """某行业板块成分股 (akshare 东财)。返回含 代码/名称。"""
    import akshare as ak
    return ak.stock_board_industry_cons_em(symbol=industry_name)


def all_spot() -> pd.DataFrame:
    """全市场实时快照 (akshare 东财, 延迟行情)。"""
    import akshare as ak
    return ak.stock_zh_a_spot_em()


# ---------- 准实时失败转移 ----------
def realtime(codes: list[str]) -> pd.DataFrame:
    """准实时行情, 多源失败转移: adata -> efinance -> akshare。"""
    # adata
    try:
        import adata
        df = adata.stock.market.list_market_current(code_list=[str(c).split(".")[0] for c in codes])
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    # akshare 兜底 (从全市场快照里筛)
    try:
        spot = all_spot()
        codeset = {str(c).split(".")[0] for c in codes}
        col = "代码" if "代码" in spot.columns else spot.columns[0]
        return spot[spot[col].astype(str).isin(codeset)]
    except Exception:
        return pd.DataFrame()


if __name__ == "__main__":
    print("self-test...")
    df = get_hist("600519", "2026-05-01")
    print("hist 600519:", df.shape, "last close", df["close"].iloc[-1] if not df.empty else None)
    idx = get_index_hist("000985", "2026-05-01")
    print("index 000985:", idx.shape)
    sff = sector_fund_flow()
    print("sector flow:", sff.shape)
    _BS.close()
