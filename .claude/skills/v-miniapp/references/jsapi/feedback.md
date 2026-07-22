# Feedback APIs

APIs for user feedback dialogs and notifications.

---

## alert

**When to use:** Show alert dialog with message.

**Basic usage (async):**
```tsx
await apisAsync.alert({
  title: 'Alert',
  content: 'Something happened'
})
```

**Key options:**
- `title`: `string` - Alert title
- `content`: `string` - Alert message

---

## confirm

**When to use:** Show confirmation dialog (OK/Cancel).

**Basic usage (async):**
```tsx
const confirmed = await apisAsync.confirm({
  title: 'Confirm',
  content: 'Are you sure?'
})
// confirmed - boolean (true if OK clicked)
```

**Key options:**
- `title`: `string` - Dialog title
- `content`: `string` - Dialog message

**Returns:** `boolean` - `true` if user confirmed, `false` if cancelled.

---

## prompt

**When to use:** Show input dialog for user text input.

**Basic usage (async):**
```tsx
const result = await apisAsync.prompt({
  title: 'Enter name',
  placeholder: 'Your name'
})
// result - user input string or null if cancelled
```

**Key options:**
- `title`: `string` - Dialog title
- `placeholder`: `string` - Input placeholder

**Returns:** `string | null` - User input or `null` if cancelled.

---

## showToast

**When to use:** Show toast notification.

**Basic usage (async):**
```tsx
await apisAsync.showToast({
  content: 'Success!',
  type: 'success',
  duration: 2000
})
```

**Key options:**
- `content`: `string` - Toast message
- `type`: `'success' | 'error' | 'loading' | ...` - Toast type
- `duration`: `number` - Display duration in ms

---

## showLoading

**When to use:** Show loading indicator.

**Basic usage (async):**
```tsx
await apisAsync.showLoading({
  content: 'Loading...'
})
```

**Key options:**
- `content`: `string` - Loading message

**Note:** Use `hideLoading()` to hide the loading indicator.

---

## hideLoading

**When to use:** Hide loading indicator.

**Basic usage (async):**
```tsx
await apisAsync.hideLoading()
```

---

## showActionSheet

**When to use:** Show action sheet (bottom menu with options).

**Basic usage (async):**
```tsx
const selected = await apisAsync.showActionSheet({
  itemList: ['Option 1', 'Option 2', 'Cancel']
})
// selected - index of selected item or -1 if cancelled
```

**Key options:**
- `itemList`: `string[]` - Array of option labels

**Returns:** `number` - Index of selected item, or `-1` if cancelled.
