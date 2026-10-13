"""Tushare HTTP protocol; no pandas dependency, tokens never logged."""

import json
import os
import time

import httpx

from app.settings import token


class ProviderError(RuntimeError):
    pass


class PermissionDenied(ProviderError):
    pass


class Tushare:
    def __init__(self, credential=None, client=None, interval=None):
        self.credential = credential if credential is not None else token()
        if not self.credential:
            raise PermissionDenied("未配置 TUSHARE_TOKEN；请在项目根目录 .env 中配置。")
        self.client = client or httpx.Client(timeout=45)
        self.interval = (
            float(os.getenv("TUSHARE_MIN_INTERVAL", "1.3")) if interval is None else interval
        )
        self.last_call = 0.0

    def close(self):
        self.client.close()

    def query(self, api, fields="", **params):
        for attempt in range(4):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            try:
                response = self.client.post(
                    "https://api.tushare.pro",
                    json={
                        "api_name": api,
                        "token": self.credential,
                        "params": params,
                        "fields": fields,
                    },
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError):
                if attempt == 3:
                    raise ProviderError(f"{api}: 网络或响应异常，重试后仍失败") from None
                time.sleep(2**attempt)
                continue
            if payload.get("code") != 0:
                msg = str(payload.get("msg", "接口异常")).replace(self.credential, "[redacted]")
                if any(term in msg.lower() for term in ["每分钟", "每秒", "频次", "rate limit"]):
                    if attempt < 3:
                        time.sleep(10 * (attempt + 1))
                        continue
                if any(term in msg.lower() for term in ["权限", "积分", "token", "每天", "每小时"]):
                    raise PermissionDenied(f"{api}: {msg}")
                raise ProviderError(f"{api}: {msg}")
            data = payload.get("data")
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("fields"), list)
                or not isinstance(data.get("items"), list)
            ):
                raise ProviderError(f"{api}: 数据结构异常")
            return [dict(zip(data["fields"], row, strict=True)) for row in data["items"]]
        raise ProviderError(f"{api}: 限流重试耗尽")

    def all(self, api, fields="", page_size=1000, **params):
        result, seen = [], set()
        for offset in range(0, 1_000_000, page_size):
            rows = self.query(api, fields, limit=page_size, offset=offset, **params)
            if not rows:
                return result
            keys = {json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows}
            if seen.intersection(keys):
                raise ProviderError(f"{api}: 分页重复，拒绝把截断结果当成完整数据")
            if len(keys) != len(rows):
                raise ProviderError(f"{api}: 返回重复记录")
            result.extend(rows)
            seen.update(keys)
            if len(rows) < page_size:
                return result
        raise ProviderError(f"{api}: 分页超出上限")
