"""Logins. PROD always (market data); UAT only when trading is enabled."""
from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv
from nubra_python_sdk.marketdata.market_data import MarketData
from nubra_python_sdk.refdata.instruments import InstrumentData
from nubra_python_sdk.trading.trading_data import NubraTrader


def login_prod():
    """Returns (client, market_data, instruments). Credentials come from .env."""
    client = InitNubraSdk(NubraEnv.PROD, env_creds=True)
    return client, MarketData(client), InstrumentData(client)


def login_uat():
    """Returns (client, instruments, trader). Only call when --trade was given."""
    client = InitNubraSdk(NubraEnv.UAT, env_creds=True)
    return client, InstrumentData(client), NubraTrader(client)
