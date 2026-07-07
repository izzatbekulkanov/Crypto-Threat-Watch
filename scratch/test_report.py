import sys
import os

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.report_generator import generate_docx_report

data = {
    "network": "TON",
    "address": "UQBJhT43rpFV7LlnXt_xqP0dbB-9fZIAwzupJGdUM2xfHp8d",
    "status": "active",
    "current_balance": "100.0 GRAM",
    "total_income": "1000.0 GRAM",
    "total_outcome": "900.0 GRAM",
    "net_balance": "100.0 GRAM",
    "total_volume": "1900.0 GRAM",
    "tx_count": 10,
    "assets": [
        {
            "symbol": "GRAM",
            "is_native": True,
            "balance": "100.0 GRAM",
            "income": "1000.0 GRAM",
            "outcome": "900.0 GRAM",
            "net": "100.0 GRAM",
            "volume": "1900.0 GRAM",
            "tx_count": 10
        }
    ],
    "yearly_stats": {"2026": {"in": 1000.0, "out": 900.0}},
    "swaps": [
        {
            "timestamp": 1782987600,
            "tx_hash": "abcdef1234567890",
            "from_desc": "10 TON",
            "to_desc": "5 USDT"
        }
    ],
    "normal_transfers": [
        {
            "tx_hash": "tx11111111111111111111111111111111111111",
            "timestamp": 1782900000,
            "symbol": "GRAM",
            "amount": 250.0,
            "direction": "in",
            "counterparty": "UQARdy8e6SSYcQG_OlKn93Y2yrKIVGWd2_QCsTWwdzOoeNYV"
        },
        {
            "tx_hash": "tx22222222222222222222222222222222222222",
            "timestamp": 1782910000,
            "symbol": "GRAM",
            "amount": 150.0,
            "direction": "out",
            "counterparty": "UQCq2bp7O5hSLp2N8BvxlppERrr0uHOLsVOno17F-swuzqjz"
        },
        {
            "tx_hash": "tx33333333333333333333333333333333333333",
            "timestamp": 1782920000,
            "symbol": "USDT",
            "amount": 500.0,
            "direction": "in",
            "counterparty": "UQA6AwfU14d6gZZ6f0-jhUclH3-hkwsvucKgh2stgNN6lBOr"
        }
    ],
    "common_links": [
        {
            "shared_address": "UQSharedC111111111111111111111111111111111111111",
            "related_wallet": "UQRelatedA22222222222222222222222222222222222222",
            "related_dir": "in",
            "related_amount": 10.0,
            "related_symbol": "GRAM",
            "related_time": 1782905000,
            "current_dir": "out",
            "current_amount": 5.5,
            "current_symbol": "GRAM",
            "current_time": 1782915000
        }
    ]
}

try:
    generate_docx_report(
        data=data,
        risk_level="🟠 HIGH",
        risk_emoji="🟠",
        lang="uz",
        output_path="scratch/test_output.docx"
    )
    print("SUCCESS: Word report generated at scratch/test_output.docx")
except Exception as e:
    import traceback
    print("FAILED:")
    traceback.print_exc()
