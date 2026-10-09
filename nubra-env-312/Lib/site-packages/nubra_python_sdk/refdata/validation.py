#src/nubra_python_sdk/refdata/validation.py
from pydantic import BaseModel, field_validator, Field, ConfigDict # type: ignore
from typing import Optional, Dict
import math


class InstrumentFinder(BaseModel):
    exchange: Optional[str] = None
    asset: Optional[str] = None
    derivative_type: Optional[str] = None
    asset_type: Optional[str] = None
    expiry: Optional[int] = None  # Store as integer internally
    strike_price: Optional[int] = None
    option_type: Optional[str] = None
    isin: Optional[str] = None

    @field_validator("expiry","strike_price", mode="before")
    @classmethod
    def parse_expiry(cls, v):
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v




class InstrumentDataWrapper(BaseModel):
    """
    Represents financial instrument data, including details such as the reference ID,
    zanskar ID, stock name, asset type, exchange, option type, and more. This class is used 
    to manage the data related to various financial instruments and their associated attributes.

    Attributes:
        ref_id (int): The reference ID of the instrument.
        nubra_id (Optional[float]): The Zanskar ID of the instrument, if available.
        option_type (Optional[str]): The option type (e.g., 'call', 'put'), if applicable.
        token (int): The token associated with the instrument.
        stock_name (str): The name of the stock.
        zanskar_name (str): The Zanskar name of the instrument.
        lot_size (int): The lot size of the instrument.
        asset (str): The asset associated with the instrument.
        exchange (str): The exchange where the instrument is listed.
        derivative_type (str): The derivative type, e.g., 'future', 'option'.
        isin (Optional[str]): The ISIN (International Securities Identification Number) of the instrument, if available.
        asset_type (str): The asset type (e.g., 'equity', 'commodity').
        tick_size (float): The tick size of the instrument.
        prev_close (Optional[float]): The previous closing price, if available.
        underlying_prev_close (Optional[float]): The previous close price of the underlying asset, if available.
        strike_price (Optional[float]): The strike price for options, if applicable.
        expiry (Optional[int]): The expiry date for options, if applicable.
    """
    ref_id: int
    option_type: Optional[str] = None
    token: int
    stock_name: str
    nubra_name: str
    lot_size: int
    asset: str
    exchange: str
    derivative_type: str
    isin: Optional[str] = None
    asset_type: str
    tick_size: int
    underlying_prev_close: Optional[int] = None
    strike_price: Optional[int] = None
    expiry: Optional[int] = None

    @field_validator("*", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        """
        This field validator checks if a given value is empty (either an empty string or NaN)
        and converts it to None. This helps in handling missing or undefined values in the 
        data model by representing them as None.

        Args:
            v: The value to be checked, which can be any type.

        Returns:
            None if the value is empty (empty string or NaN), otherwise returns the original value.
        """
        if v == "" or (isinstance(v, float) and math.isnan(v)):
            return None
        return v
    
    model_config = ConfigDict(
        from_attributes=True,     # ✅ replaces orm_mode
        populate_by_name=True     # ✅ still valid
    )
