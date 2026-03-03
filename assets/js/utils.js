/**
 * 立米AI Ryu兵衛 - 共通ユーティリティ関数
 */

const utils = {
    /**
     * 画像をクライアントサイドでリサイズ＆JPEG圧縮する
     * @param {File} file - 元の画像ファイル
     * @param {number} maxWidth - 最大幅
     * @param {number} maxHeight - 最大高さ
     * @param {number} quality - JPEG品質（0.0 〜 1.0）
     * @returns {Promise<File>} 圧縮されたFileオブジェクト
     */
    compressImage(file, maxWidth = 1600, maxHeight = 1600, quality = 0.7) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();

            reader.onload = (e) => {
                const img = new Image();
                img.onload = () => {
                    let width = img.width;
                    let height = img.height;

                    // 縮小倍率（1より大きくしない = アップスケールしない）
                    const scale = Math.min(maxWidth / width, maxHeight / height, 1);

                    const canvas = document.createElement("canvas");
                    canvas.width = Math.round(width * scale);
                    canvas.height = Math.round(height * scale);

                    const ctx = canvas.getContext("2d");
                    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

                    canvas.toBlob(
                        (blob) => {
                            if (!blob) {
                                reject(new Error("画像圧縮に失敗しました"));
                                return;
                            }
                            // 元の拡張子に関わらず jpeg に統一
                            const newName = file.name.replace(/\.(png|jpg|jpeg|webp|heic)$/i, "") + ".jpg";
                            const compressedFile = new File([blob], newName, { type: "image/jpeg" });
                            resolve(compressedFile);
                        },
                        "image/jpeg",
                        quality
                    );
                };
                img.onerror = () => reject(new Error("画像のデコードに失敗しました"));
                img.src = e.target.result;
            };

            reader.onerror = () => reject(new Error("ファイルの読み込みに失敗しました"));
            reader.readAsDataURL(file);
        });
    },

    /**
     * 日時文字列を「YYYY-MM-DD HH:mm」形式にフォーマット
     * @param {string} dateString 
     * @returns {string}
     */
    formatDateTime(dateString) {
        if (!dateString) return "-";
        try {
            const d = new Date(dateString);
            if (isNaN(d.getTime())) return dateString.replace("T", " ").slice(0, 16);

            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            const hours = String(d.getHours()).padStart(2, '0');
            const minutes = String(d.getMinutes()).padStart(2, '0');
            return `${year}-${month}-${day} ${hours}:${minutes}`;
        } catch (e) {
            return dateString;
        }
    },

    /**
     * XSS対策用 HTMLエスケープ
     * @param {string} str 
     * @returns {string}
     */
    escapeHtml(str) {
        if (str == null) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
};
