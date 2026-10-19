"""Test whatthepatch with use_patch=True (fuzzy mode)."""
import sys
sys.path.insert(0, 'src')
from pathlib import Path
import whatthepatch

SERVICES = Path(r'C:\Users\lnellutl\Downloads\aie-forge-main\services')
f = SERVICES / 'account-service/src/index.js'
original = f.read_bytes().replace(b'\r\n', b'\n').decode('utf-8')

diff_text = """\
--- a/account-service/src/index.js
+++ b/account-service/src/index.js
@@ -10,11 +10,18 @@
 app.use(cors());
 app.use(express.json());
 
-// Request logging
+// Request and response logging
 app.use((req, res, next) => {
-  console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
+  const startTime = Date.now();
+  console.log(`[${new Date().toISOString()}] INCOMING: ${req.method} ${req.originalUrl}`);
+
+  res.on('finish', () => {
+    const duration = Date.now() - startTime;
+    console.log(`[${new Date().toISOString()}] OUTGOING: ${req.method} ${req.originalUrl} ${res.statusCode}`);
+  });
+
   next();
 });
+
 // Health check
 app.get('/health', (req, res) => {
"""

patches = list(whatthepatch.parse_patch(diff_text))
patch = patches[0]

# Try use_patch=True (applies changes without strict context checking)
try:
    result = whatthepatch.apply_diff(patch, original, use_patch=True)
    if result:
        result_str = '\n'.join(result)
        print("SUCCESS with use_patch=True!")
        lines = result_str.splitlines()
        print(f"Lines: {len(original.splitlines())} -> {len(lines)}")
        for i, l in enumerate(lines[8:22], 9):
            print(f"  {i}: {l}")
    else:
        print("FAILED: returned None")
except Exception as e:
    print(f"FAILED: {e}")

# Also try use_patch=False
try:
    result2 = whatthepatch.apply_diff(patch, original, use_patch=False)
    if result2:
        print("\nSUCCESS with use_patch=False!")
    else:
        print("\nFAILED with use_patch=False: returned None")
except Exception as e:
    print(f"\nFAILED with use_patch=False: {e}")
