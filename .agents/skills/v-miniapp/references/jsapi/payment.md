# Payment APIs

APIs for payment methods and payment processing.

---

## showPaymentMethod

**When to use:** Show payment method selection UI.

**Basic usage (async):**
```tsx
await apisAsync.showPaymentMethod()
```

**Note:** Opens native payment method selection interface.

---

## getDefaultPaymentMethod

**When to use:** Get user's default payment method.

**Basic usage (async):**
```tsx
const paymentMethod = await apisAsync.getDefaultPaymentMethod()
```

**Returns:** Default payment method information.

---

## initPayment

**When to use:** Initialize a payment transaction.

**Basic usage (async):**
```tsx
const result = await apisAsync.initPayment({
  // payment options
})
```

**Key options:**
- Payment configuration (check API docs for full options)

**Note:** Initiates payment flow. User will see payment confirmation UI.
