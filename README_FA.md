# نقشه‌ی پروژه
1. یک ریپوی عمومی جدید بساز (مثلاً `pesteh-graph`) و این پوشه را در آن بریز.
2. در `.github/workflows/graph.yml` سه آدرس `YOUR_USER/...` را با ریپوهای واقعی عوض کن.
3. Settings → Pages → Source: شاخه‌ی main و پوشه‌ی `/docs`.
4. صفحه روی مانیتور باز بماند؛ هر دقیقه خودش graph.json را دوباره می‌خواند.
   بخش‌ها و اتصال‌های جدید (۷ روز اخیر) زرد و چشمک‌زن می‌شوند.
اجرای محلی: `python analyze.py --android A --windows W --web public_html -o docs/graph.json`
