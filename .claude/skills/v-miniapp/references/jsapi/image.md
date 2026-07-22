# Image APIs

APIs for image selection, preview, and processing.

---

## chooseImage

**When to use:** Open image picker to select image(s) from gallery or camera.

**Basic usage (async):**
```tsx
const result = await apisAsync.chooseImage({
  count: 1,
  sourceType: ['album', 'camera']
})
// result.filePaths - array of selected image file paths
```

**Key options:**
- `count`: `number` - Maximum number of images to select
- `sourceType`: `('album' | 'camera')[]` - Image sources

**Returns:**
- `filePaths`: `string[]` - Array of selected image file paths

---

## previewImage

**When to use:** Preview image(s) in fullscreen viewer.

**Basic usage (async):**
```tsx
await apisAsync.previewImage({
  urls: ['https://example.com/image.jpg'],
  current: 0
})
```

**Key options:**
- `urls`: `string[]` - Array of image URLs to preview
- `current`: `number` - Index of initially displayed image

---

## compressImage

**When to use:** Compress image to reduce file size.

**Basic usage (async):**
```tsx
const result = await apisAsync.compressImage({
  src: '/path/to/image.jpg',
  quality: 80
})
// result.tempFilePath - compressed image path
```

**Key options:**
- `src`: `string` - Source image file path
- `quality`: `number` - Compression quality (0-100)

**Returns:**
- `tempFilePath`: `string` - Path to compressed image
