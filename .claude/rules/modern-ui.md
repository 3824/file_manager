# Modern UI Guidelines for PyQt6/PySide6

## Design Principles
- **Flat & Minimal**: 影やグラデーションは控えめにし、フラットデザインを採用する。
- **Color Palette**: 
  - Primary: #6200EE (Deep Purple)
  - Background: #121212 (Dark Material)
  - Surface: #1E1E1E
  - Text: #FFFFFF (High Emphasis), #B0B0B0 (Medium Emphasis)
- **Spacing**: 余白は8pxの倍数（8, 16, 24, 32...）を使用する。
- **Typography**: システムフォント（Segoe UI, Roboto）を使用し、サイズは14pxを基準とする。

## Implementation Rules (QSS)
- すべてのウィジェットはQSS (Qt Style Sheets) でスタイリングする。
- 角丸は `border-radius: 8px` を標準とする。
- ボタンのホバーエフェクト（`QPushButton:hover`）を必ず実装する。
