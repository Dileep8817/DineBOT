import { useEffect, useState } from "react";
import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from "@stripe/react-stripe-js";
import axios from "axios";
import { apiUrl } from "./apiConfig";

const pk = process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY;
const stripePromise = pk ? loadStripe(pk) : null;

function PayForm({ onSuccess, onError }) {
  const stripe = useStripe();
  const elements = useElements();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!stripe || !elements) return;
    const baseUrl = window.location.href.split("#")[0].split("?")[0];
    const { error, paymentIntent } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: `${baseUrl}?paid=1` },
      redirect: "if_required",
    });
    if (error) {
      onError(error.message || "Payment failed");
      return;
    }
    if (paymentIntent && paymentIntent.status === "succeeded") {
      onSuccess();
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <PaymentElement />
      <button type="submit" style={{ marginTop: 12 }}>
        Pay now
      </button>
    </form>
  );
}

export function StripeCheckout({
  orderId,
  orderNumber,
  sessionId,
  onClose,
  onPaid,
}) {
  const [clientSecret, setClientSecret] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (!pk) {
      setErr("Missing REACT_APP_STRIPE_PUBLISHABLE_KEY");
      return () => {};
    }
    if (orderId == null) return () => {};

    (async () => {
      try {
        const res = await axios.post(apiUrl("/payments/create-intent"), {
          order_id: orderId,
          session_id: sessionId,
        });
        if (!cancelled) setClientSecret(res.data.client_secret);
      } catch (e) {
        if (!cancelled) {
          setErr(
            (typeof e.response?.data?.detail === "string"
              ? e.response.data.detail
              : null) ||
              e.message ||
              "Could not start payment"
          );
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [orderId, sessionId]);

  if (err) {
    return (
      <div style={{ padding: 16, background: "#fff", borderRadius: 8, maxWidth: 420 }}>
        <p style={{ margin: "0 0 12px" }}>{err}</p>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
    );
  }

  if (!clientSecret) {
    return <p style={{ padding: 16 }}>Loading payment form…</p>;
  }

  return (
    <div style={{ padding: 16, background: "#fff", borderRadius: 8, maxWidth: 480 }}>
      <h3 style={{ marginTop: 0 }}>Complete payment</h3>
      <p style={{ marginTop: 0, fontSize: 14, color: "#444" }}>
        {orderNumber
          ? `Order ${orderNumber} (id ${orderId})`
          : `Order #${orderId}`}
      </p>
      <Elements stripe={stripePromise} options={{ clientSecret, appearance: { theme: "stripe" } }}>
        <PayForm
          onSuccess={() => onPaid && onPaid()}
          onError={(m) => setErr(m)}
        />
      </Elements>
      <button type="button" style={{ marginTop: 12 }} onClick={onClose}>
        Cancel
      </button>
    </div>
  );
}