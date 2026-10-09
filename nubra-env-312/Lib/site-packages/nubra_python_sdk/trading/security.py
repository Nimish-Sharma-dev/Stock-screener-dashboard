#src/nubra_python_sdk/trading/security.py
import os
import json
import webbrowser

from typing import Union, List

import pandas as pd # type: ignore
import requests # type: ignore
from pydantic import ValidationError # type: ignore


from nubra_python_sdk.start_sdk import InitNubraSdk
from nubra_python_sdk.interceptor.htttpclient import BaseHttpClient
from nubra_python_sdk.interceptor.errors import NubraValidationError
from nubra_python_sdk.trading.validation import (
    StockItem, 
    EdisResponse,
    EdisHoldingRefIDS, 
    StockNonEdis,
    EdisHoldingsResponse
    )

import logging
logger= logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
print = lambda *args, **kwargs: None


class NubraEdisClient(InitNubraSdk):
    """eDIS (electronic Delivery Instruction Slip) integration helpers.

    This module encapsulates the minimal workflow required to initiate and
    track an eDIS mandate with CDSL from client-facing Nubra SDK code.
    """

    def __init__(self, client: InitNubraSdk):
        """
        Initializes the Trading Data instance using the provided Nubra SDK client.

        Args:
            client (InitNubraSdk): An authenticated instance of InitNubraSdk.
        """
        self.api_base_url = client.API_BASE_URL
        self.db_path= client.db_path
        self.client = BaseHttpClient(self)

    def _url(self, path):
        """
        Constructs the full API URL for a given endpoint path.

        Args:
            path (str): Relative API path.

        Returns:
            str: Full API URL.
        """
        return f"{self.api_base_url}/{path}"
    

    def init_edis(self, request: Union[List[dict], dict]):
        """
        Opens the default web browser to enter T-Pin.

        Args:
            request: Union[List[dict], dict]  eg. request=[{"ref_id": 2344, "quantity":1}]
            ref_id (int): The ref_id of the security
            quantity (int): The quantity of the security.
        Returns:
            The response containing the status of the operation.
        """
        if isinstance(request, dict):
            try:
                request= [StockItem(**request)]
            except ValidationError as ve:
                return {"message": ve.errors()}
            
        elif isinstance(request, list) and request and isinstance(request[0], dict):
            try:
                request= [StockItem(**item) for item in request]
            except ValidationError as ve:
                return {"message": ve.errors()}
            
        payload = {
            "stocks": [ts.model_dump(by_alias=True) for ts in request]
        }
        path= "depository/init_edis"
        try: 
            respone= self.client.request("post", self._url(path), json= payload)
            result= EdisResponse(**respone.json())
            if result:
                edis_link= result.redirect_url
                if edis_link:
                    webbrowser.open_new(edis_link)
            return result.message
        except ValidationError as ve:
            raise NubraValidationError(ve.errors())
        

    def non_edis_holdings(self):
        path = "depository/non_edis_holdings"
        try:
            response= self.client.request("get", self._url(path))
            if response.json() is None:
                return []
            return StockNonEdis(**response.json())
        except ValidationError as ve:
            raise NubraValidationError(ve.errors())


    def edis_holdings(self):
        path= "depository/edis_holdings"
        try:
            response= self.client.request("get", self._url(path))
            if response.json() is None:
                return []
            return EdisHoldingsResponse(**response.json())
        except ValidationError as ve:
            raise NubraValidationError(ve.errors())

        
    def edis_holdings_refids(self, ref_ids: List[int]):
        path= "depository/edis_holdings_for_refIds"
        try:
            response= self.client.request("post",self._url(path), json= ref_ids)
            if response.json() is None:
                return []
            return EdisHoldingRefIDS(**response.json())
        except ValidationError as ve:
            raise NubraValidationError(ve.errors())





    
    



        

        

        
    

