/** Demo failure payloads for the footer “Play” → live console CTA. */

export type DemoFailureId =
  | "insufficient_funds"
  | "bank_technical_error"
  | "payment_cancelled"
  | "fraud_suspect";

export type FailedPaymentPayload = {
  payment_id: string;
  order_id?: string;
  customer_id?: string;
  amount_paise: number;
  currency?: string;
  method?: string;
  error_code?: string;
  error_description?: string;
  error_reason?: string;
  customer_name?: string;
  merchant_name?: string;
};

export type DemoFailure = {
  id: DemoFailureId;
  label: string;
  strategy: string;
  branch: string;
  /** Base fields; payment_id is stamped unique at click time. */
  payload: Omit<FailedPaymentPayload, "payment_id">;
};

export const DEMO_FAILURES: DemoFailure[] = [
  {
    id: "insufficient_funds",
    label: "Insufficient funds",
    strategy: "offer_partial_payment (or alternate)",
    branch: "path_partial → path_alternate",
    payload: {
      customer_id: "cust_demo_priya",
      amount_paise: 249900,
      method: "card",
      error_code: "BAD_REQUEST_ERROR",
      error_description: "Payment failed due to insufficient funds",
      error_reason: "insufficient_funds",
      customer_name: "Priya",
      merchant_name: "Acme Store",
    },
  },
  {
    id: "bank_technical_error",
    label: "Bank technical error",
    strategy: "delay_and_retry",
    branch: "path_delay → Celery",
    payload: {
      customer_id: "cust_demo_meera",
      amount_paise: 320000,
      method: "netbanking",
      error_code: "GATEWAY_ERROR",
      error_description: "Netbanking is temporarily unavailable at the bank",
      error_reason: "bank_not_available",
      customer_name: "Meera",
      merchant_name: "Acme Store",
    },
  },
  {
    id: "payment_cancelled",
    label: "User dropped",
    strategy: "retry_same_method",
    branch: "path_retry",
    payload: {
      customer_id: "cust_demo_arjun",
      amount_paise: 99900,
      method: "upi",
      error_code: "GATEWAY_ERROR",
      error_description: "Bank timed out while authorizing UPI payment",
      error_reason: "bank_timeout",
      customer_name: "Arjun",
      merchant_name: "Acme Store",
    },
  },
  {
    id: "fraud_suspect",
    label: "Risk / unknown",
    strategy: "escalate_to_human",
    branch: "path_escalate",
    payload: {
      customer_id: "cust_demo_risk",
      amount_paise: 500000,
      method: "card",
      error_code: "BAD_REQUEST_ERROR",
      error_description: "Unrecognized decline — possible risk signal",
      error_reason: "unrecognized_risk_signal",
      customer_name: "Dev",
      merchant_name: "Acme Store",
    },
  },
];

export function buildDemoPayment(demo: DemoFailure): FailedPaymentPayload {
  const stamp = Date.now().toString(36);
  return {
    ...demo.payload,
    payment_id: `pay_demo_${demo.id}_${stamp}`,
    order_id: `order_demo_${stamp}`,
  };
}
