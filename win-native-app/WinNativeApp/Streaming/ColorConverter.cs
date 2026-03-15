namespace WinNativeApp.Streaming;

/// <summary>
/// BGRA → NV12 変換。パイプ転送量を63%削減する（3.7MB → 1.4MB @1280x720）。
/// NV12レイアウト: Y平面 (W×H bytes) + UV平面 (W×H/2 bytes, U/Vインターリーブ)
/// </summary>
public static class ColorConverter
{
    /// <summary>
    /// NV12バッファのサイズを計算する。
    /// </summary>
    public static int Nv12Size(int width, int height) => width * height * 3 / 2;

    /// <summary>
    /// BGRA → NV12 変換（BT.601係数）。
    /// bgra: 入力 BGRA バイト配列 (W×H×4 bytes)
    /// nv12: 出力 NV12 バイト配列 (W×H×1.5 bytes)
    /// </summary>
    public static unsafe void BgraToNv12(byte[] bgra, byte[] nv12, int width, int height)
    {
        int yPlaneSize = width * height;
        int uvOffset = yPlaneSize;

        fixed (byte* pBgra = bgra, pNv12 = nv12)
        {
            for (int y = 0; y < height; y++)
            {
                int rowOffset = y * width;
                byte* srcRow = pBgra + rowOffset * 4;
                byte* yRow = pNv12 + rowOffset;

                // Y平面: 全ピクセル
                for (int x = 0; x < width; x++)
                {
                    byte b = srcRow[x * 4];
                    byte g = srcRow[x * 4 + 1];
                    byte r = srcRow[x * 4 + 2];

                    // BT.601: Y = ((66*R + 129*G + 25*B + 128) >> 8) + 16
                    int yVal = ((66 * r + 129 * g + 25 * b + 128) >> 8) + 16;
                    yRow[x] = (byte)(yVal < 0 ? 0 : yVal > 255 ? 255 : yVal);
                }

                // UV平面: 偶数行のみ（2x2サブサンプリング）
                if ((y & 1) == 0)
                {
                    byte* uvRow = pNv12 + uvOffset + (y / 2) * width;

                    for (int x = 0; x < width; x += 2)
                    {
                        // 2x2ブロックの左上ピクセルからU/Vを取得
                        byte b = srcRow[x * 4];
                        byte g = srcRow[x * 4 + 1];
                        byte r = srcRow[x * 4 + 2];

                        // BT.601: U = ((-38*R - 74*G + 112*B + 128) >> 8) + 128
                        int u = ((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128;
                        // BT.601: V = ((112*R - 94*G - 18*B + 128) >> 8) + 128
                        int v = ((112 * r - 94 * g - 18 * b + 128) >> 8) + 128;

                        uvRow[x]     = (byte)(u < 0 ? 0 : u > 255 ? 255 : u);
                        uvRow[x + 1] = (byte)(v < 0 ? 0 : v > 255 ? 255 : v);
                    }
                }
            }
        }
    }
}
