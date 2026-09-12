"""One-off script (not part of the shipped package) that builds data/coarse_map.json
by hand-classifying each of the 77 Banking77 fine intents into one of the 10 coarse
groups named in SPEC-model-bench.md section 3.2. Run once during W-A1; the output
file is what ships. Kept in the repo root (not src/) so it is obviously not part of
the runtime package.
"""
import json

GROUPS = {
    "card", "transfers_payments", "top_up", "atm_cash", "account_identity",
    "fees_charges_rates", "disputes_fraud", "refunds_cancellations",
    "app_pin_access", "currency_crypto",
}

# Rule of thumb used to classify (documented in README.md so a reader can challenge it):
#   card                 -> physical/virtual card lifecycle: ordering, arrival, activation,
#                            linking, replacement, expiry, acceptance, "not working" (non-fraud)
#   transfers_payments   -> sending/receiving money, transfer or payment status/timing,
#                            cancellations of a transfer in progress (not refunds)
#   top_up               -> adding funds to the account by any method, and top-up specific
#                            issues, including a balance not updating after a deposit/transfer in
#   atm_cash             -> ATM and cash withdrawal specific issues (including a swallowed card)
#   account_identity     -> identity verification, personal details, account status
#   fees_charges_rates   -> a fee, charge, or rate question/complaint not specific to topping up
#   disputes_fraud       -> unrecognized/duplicate/fraudulent charges, lost/stolen/compromised
#   refunds_cancellations-> refund requests/status, cancelling a subscription-like arrangement
#   app_pin_access       -> PIN and passcode issues
#   currency_crypto      -> currency exchange rates, supported currencies/cards/payment methods,
#                            country support (the "compatibility" bucket)
MAPPING = {
    "card_arrival": "card",
    "card_linking": "card",
    "exchange_rate": "currency_crypto",
    "card_payment_wrong_exchange_rate": "fees_charges_rates",
    "extra_charge_on_statement": "fees_charges_rates",
    "pending_cash_withdrawal": "atm_cash",
    "fiat_currency_support": "currency_crypto",
    "card_delivery_estimate": "card",
    "automatic_top_up": "top_up",
    "card_not_working": "card",
    "exchange_via_app": "currency_crypto",
    "lost_or_stolen_card": "disputes_fraud",
    "age_limit": "account_identity",
    "pin_blocked": "app_pin_access",
    "contactless_not_working": "card",
    "top_up_by_bank_transfer_charge": "top_up",
    "pending_top_up": "top_up",
    "cancel_transfer": "transfers_payments",
    "top_up_limits": "top_up",
    "wrong_amount_of_cash_received": "atm_cash",
    "card_payment_fee_charged": "fees_charges_rates",
    "transfer_not_received_by_recipient": "transfers_payments",
    "supported_cards_and_currencies": "currency_crypto",
    "getting_virtual_card": "card",
    "card_acceptance": "card",
    "top_up_reverted": "top_up",
    "balance_not_updated_after_cheque_or_cash_deposit": "top_up",
    "card_payment_not_recognised": "disputes_fraud",
    "edit_personal_details": "account_identity",
    "why_verify_identity": "account_identity",
    "unable_to_verify_identity": "account_identity",
    "get_physical_card": "card",
    "visa_or_mastercard": "currency_crypto",
    "topping_up_by_card": "top_up",
    "disposable_card_limits": "card",
    "compromised_card": "disputes_fraud",
    "atm_support": "atm_cash",
    "direct_debit_payment_not_recognised": "disputes_fraud",
    "passcode_forgotten": "app_pin_access",
    "declined_cash_withdrawal": "atm_cash",
    "pending_card_payment": "transfers_payments",
    "lost_or_stolen_phone": "disputes_fraud",
    "request_refund": "refunds_cancellations",
    "declined_transfer": "transfers_payments",
    "Refund_not_showing_up": "refunds_cancellations",
    "declined_card_payment": "transfers_payments",
    "pending_transfer": "transfers_payments",
    "terminate_account": "account_identity",
    "card_swallowed": "atm_cash",
    "transaction_charged_twice": "disputes_fraud",
    "verify_source_of_funds": "account_identity",
    "transfer_timing": "transfers_payments",
    "reverted_card_payment?": "transfers_payments",
    "change_pin": "app_pin_access",
    "beneficiary_not_allowed": "transfers_payments",
    "transfer_fee_charged": "fees_charges_rates",
    "receiving_money": "transfers_payments",
    "failed_transfer": "transfers_payments",
    "transfer_into_account": "transfers_payments",
    "verify_top_up": "top_up",
    "getting_spare_card": "card",
    "top_up_by_cash_or_cheque": "top_up",
    "order_physical_card": "card",
    "virtual_card_not_working": "card",
    "wrong_exchange_rate_for_cash_withdrawal": "atm_cash",
    "get_disposable_virtual_card": "card",
    "top_up_failed": "top_up",
    "balance_not_updated_after_bank_transfer": "top_up",
    "cash_withdrawal_not_recognised": "disputes_fraud",
    "exchange_charge": "fees_charges_rates",
    "top_up_by_card_charge": "top_up",
    "activate_my_card": "card",
    "cash_withdrawal_charge": "fees_charges_rates",
    "card_about_to_expire": "card",
    "apple_pay_or_google_pay": "currency_crypto",
    "verify_my_identity": "account_identity",
    "country_support": "currency_crypto",
}


def main():
    with open("data/_labels.json") as f:
        labels = json.load(f)

    assert len(labels) == 77, f"expected 77 labels, got {len(labels)}"
    assert set(labels) == set(MAPPING), (
        "mismatch between dataset labels and MAPPING keys:\n"
        f"in labels not mapping: {set(labels) - set(MAPPING)}\n"
        f"in mapping not labels: {set(MAPPING) - set(labels)}"
    )
    assert set(MAPPING.values()) <= GROUPS, f"unknown group used: {set(MAPPING.values()) - GROUPS}"
    assert len(MAPPING) == 77

    from collections import Counter
    counts = Counter(MAPPING.values())
    print("group counts:")
    for g in sorted(GROUPS):
        print(f"  {g}: {counts.get(g, 0)}")
    print("groups used:", len(counts), "/ 10")

    with open("data/coarse_map.json", "w") as f:
        json.dump(MAPPING, f, indent=2, sort_keys=True)
    print("wrote data/coarse_map.json")


if __name__ == "__main__":
    main()
