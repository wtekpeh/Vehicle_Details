"""
lookup.py

This module is responsible for:
1. Calling the Vehicle Data Global API.
2. Parsing the API response safely.
3. Returning structured lookup results for the rest of the application.

Why this module exists
----------------------
We want all API-related logic in one place so that:
- the GUI stays simple
- CSV processing stays clean
- future changes to the API only affect one file
"""

import os
from typing import Dict, Optional, TypedDict

import requests
from dotenv import load_dotenv

# Load .env variables
load_dotenv()


# =======================
# CONFIG / CONSTANTS
# =======================

VDG_API_KEY = os.getenv("VDG_API_KEY")
VDG_PACKAGE_NAME = os.getenv("VDG_PACKAGE_NAME", "VehicleDetails")

VDG_BASE_URL = "https://uk.api.vehicledataglobal.com"
VDG_LOOKUP_PATH = "/r2/lookup"


class VehicleData(TypedDict, total=False):
    """
    Vehicle data returned when a lookup succeeds.
    """
    make: str
    typeApproval: str


class LookupResult(TypedDict):
    """
    Full structured result returned by lookup_vehicle_data().

    Fields
    ------
    success:
        True if the lookup succeeded and usable data was returned.
    vehicle_data:
        Dictionary containing extracted fields like make and typeApproval.
        Empty dict if lookup failed.
    status_code:
        API status code, HTTP status code, or internal script status.
    status_message:
        Human-readable explanation of what happened.
    """
    success: bool
    vehicle_data: VehicleData
    status_code: str
    status_message: str


def lookup_vehicle_data(reg: str, cache: Dict[str, LookupResult]) -> LookupResult:
    """
    Look up vehicle data for a UK registration.

    Parameters
    ----------
    reg : str
        Cleaned registration number.
    cache : dict
        Cache of previous reg -> lookup result to avoid duplicate paid calls.

    Returns
    -------
    LookupResult
        Example success result:
        {
            "success": True,
            "vehicle_data": {
                "make": "FORD",
                "typeApproval": "M1"
            },
            "status_code": "0",
            "status_message": "Success"
        }

        Example failure result:
        {
            "success": False,
            "vehicle_data": {},
            "status_code": "13",
            "status_message": "InvalidSearchTerm"
        }
    """

    # 1. Return cached result if available
    if reg in cache:
        return cache[reg]

    # 2. Ensure API key exists
    if not VDG_API_KEY:
        raise RuntimeError(
            "VDG_API_KEY is not set. "
            "Create a .env file in the same folder as your scripts and add:\n"
            "VDG_API_KEY=your-real-api-key-here"
        )

    try:
        url = f"{VDG_BASE_URL}{VDG_LOOKUP_PATH}"

        # This API expects authentication and search term in the query string
        params = {
            "ApiKey": VDG_API_KEY,
            "PackageName": VDG_PACKAGE_NAME,
            "Vrm": reg,
        }

        response = requests.get(url, params=params, timeout=20)

        # Try to parse JSON even if HTTP code is not 200,
        # because the API may still return a useful body.
        try:
            data = response.json()
        except ValueError:
            data = {}

        # If HTTP layer failed, return that cleanly
        if response.status_code >= 400:
            result: LookupResult = {
                "success": False,
                "vehicle_data": {},
                "status_code": str(response.status_code),
                "status_message": f"HTTP error {response.status_code}",
            }
            cache[reg] = result
            return result

        # Top-level API response info
        response_info = data.get("ResponseInformation", {}) or {}
        is_success = response_info.get("IsSuccessStatusCode", False)
        api_status_code = str(response_info.get("StatusCode", ""))
        api_status_message = response_info.get("StatusMessage", "") or "Unknown API response"

        if not is_success:
            result: LookupResult = {
                "success": False,
                "vehicle_data": {},
                "status_code": api_status_code,
                "status_message": api_status_message,
            }
            cache[reg] = result
            return result

        # Navigate nested JSON safely
        results = data.get("Results", {}) or {}

        vehicle_details = results.get("VehicleDetails", {}) or {}
        vehicle_identification = vehicle_details.get("VehicleIdentification", {}) or {}

        model_details = results.get("ModelDetails", {}) or {}
        model_classification = model_details.get("ModelClassification", {}) or {}

        make = vehicle_identification.get("DvlaMake") or ""
        type_approval = model_classification.get("TypeApprovalCategory") or ""

        vehicle_data: VehicleData = {
            "make": make,
            "typeApproval": type_approval,
        }

        result: LookupResult = {
            "success": True,
            "vehicle_data": vehicle_data,
            "status_code": api_status_code or "0",
            "status_message": api_status_message or "Success",
        }

        cache[reg] = result
        return result

    except requests.exceptions.RequestException as e:
        result: LookupResult = {
            "success": False,
            "vehicle_data": {},
            "status_code": "REQUEST_EXCEPTION",
            "status_message": str(e),
        }
        cache[reg] = result
        return result

    except Exception as e:
        result: LookupResult = {
            "success": False,
            "vehicle_data": {},
            "status_code": "UNEXPECTED_ERROR",
            "status_message": str(e),
        }
        cache[reg] = result
        return result