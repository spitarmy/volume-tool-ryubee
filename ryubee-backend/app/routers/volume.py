"""AI体積見積もりルーター: 画像をOpenAI GPT-4o Visionに投げてJSONを受け取る"""
import os
import json
import base64
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from openai import AsyncOpenAI
from app.database import get_db
from app import models, auth

router = APIRouter(prefix="/v1/volume-estimate", tags=["volume"])

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# モデル定義など
SYSTEM_PROMPT = """
あなたは、不用品回収・産廃処理の「熟練のプロ」として、写真から正確な体積（立米：m³）と重量（kg）を算出するAIです。
実際の回収現場では、写真に写っている表面の荷物だけでなく、隠れた奥のスペース、タンス等の「中身」、そして積み込み時に発生する「無駄な空間（空隙）」を加味してトラックの必要台数を割り出します。

以下の【プロの体積計算ロジック】に厳密に従って算出してください：

1. 【空間ベースの算出】
写真が部屋の全体像を捉えている場合、以下の日本の標準的な部屋サイズを参考に、荷物の占有率から体積を出してください。
- 1畳（1.62 m²）に高さ1mまで荷物がある = 約1.6 m³
- 4.5畳の部屋に腰の高さ(1m)まで荷物が散乱 = 約7 m³
- 6畳の部屋に天井近く(2m)まで荷物が満載 = 約20 m³

2. 【アイテムベースの算出】
- 45Lゴミ袋1袋（実際にトラックに積む際のスペース） = 約0.08 m³ (空隙を含む)
- カラーボックス（3段） = 約0.1 m³
- 1ドア冷蔵庫 = 約0.2 m³ / 6ドア大型冷蔵庫 = 約1.0 m³
- 洗濯機 = 約0.4 m³
- シングルベッド（フレーム＋マット） = 約1.0 m³
- 軽トラック1台分満載（コンパネあり） = 約2.5 m³
- 2t平ボディトラック1台分満載 = 約5.0 m³
- 2t箱車・アルミバン1台分満載 = 約10.0 m³〜12.0 m³

3. 【隠蔽・空隙バッファ（極めて重要）】
ゴミが重なり合っている場合、または棚やタンスがある場合、見える部分の体積を計算後、必ず「空隙率・隠れた荷物」の補正として【1.5倍〜2.0倍】を掛けてください。この業界では積載オーバーは許されず、常に安全側（多め）に見積もります。

4. 【重量(kg)の算出ルール】
- 一般的な家庭ゴミ・家財の混載の場合、1m³あたり「約100kg〜150kg」です。
- タンス、本、雑誌、食器、金属、陶器など重いものが多い場合は、1m³あたり「約200kg〜300kg」に引き上げてください。
- 算出したm³に、上記の比重を掛けて `total_weight_kg` を算出してください。

【出力JSON仕様】
{
  "total_volume_m3": 12.5,
  "total_weight_kg": 1500,
  "items": [
    {"category": "ダンボール・雑ゴミ群", "quantity": 1, "volume_total_m3": 5.0},
    {"category": "大型家具", "quantity": 3, "volume_total_m3": 4.5}
  ],
  "special_disposal": {
    "recycle_items": ["冷蔵庫"],
    "hard_disposal_items": ["金庫"],
    "dangerous_items": ["スプレー缶"]
  },
  "warnings": [
    "画像が暗くて見えにくい部分があります",
    "タンスの中に中身が入っている想定で多めに見積もっています"
  ]
}

【JSONに関する厳格な注意事項】
- マークダウン(```json 等)を使用しないでください。パース可能な「生のJSONテキスト」のみを出力してください。
"""

@router.post("")
async def estimate_volume(
    env_stairs: str = Form("none"),
    env_far_parking: str = Form("false"),
    manual_items: str = Form("[]"),
    images: list[UploadFile] = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    # 1. サーバー設定情報を取得
    settings = db.query(models.CompanySettings).filter_by(company_id=current_user.company_id).first()

    import time
    import uuid

    # 画像を保存＆Base64化
    base64_images = []
    saved_file_urls = []
    os.makedirs("uploads", exist_ok=True)

    for f in images:
        content = await f.read()
        b64 = base64.b64encode(content).decode('utf-8')
        mime_type = f.content_type or "image/jpeg"
        base64_images.append(f"data:{mime_type};base64,{b64}")
        
        # ローカルへ保存 (永続化)
        ext = "jpg"
        if "png" in mime_type: ext = "png"
        elif "heic" in mime_type.lower(): ext = "heic"
        filename = f"v_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"
        filepath = os.path.join("uploads", filename)
        with open(filepath, "wb") as out_f:
            out_f.write(content)
        saved_file_urls.append(f"/uploads/{filename}")

    # OpenAIが利用可能か判定
    api_key = os.getenv("OPENAI_API_KEY")
    ai_result = None

    if api_key and api_key.startswith("sk-"):
        # GPT-4o Vision APIリクエスト構築
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        
        user_content = [
            {"type": "text", "text": f"【環境条件】\n写真枚数: {len(base64_images)}枚\n階段: {env_stairs}\n横付け不可: {env_far_parking}\n追加特例品目: {manual_items}\nこれらの画像を解析して、プロの視点から見積もり結果をJSONで出力してください。必ずJSON内に 'total_weight_kg' (数値) を含めて推定の総重量(kg)を算出し、荷物が多い場合は必ず安全バッファ（空隙率）を掛けて立米を出してください。"}
        ]
        
        for b64 in base64_images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": b64}
            })
            
        messages.append({"role": "user", "content": user_content})

        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                response_format={ "type": "json_object" },
                max_tokens=1500,
                temperature=0.2
            )
            ai_content = response.choices[0].message.content
            ai_result = json.loads(ai_content)
            
            # Mathematical Safety Floor (Softened)
            # Only apply if it's clearly a multi-photo job, but with a more realistic minimal bounding (0.3m3 per photo)
            img_count = len(base64_images)
            safety_floor = img_count * 0.3
            if img_count < 3:
                safety_floor = 0.5  # Absolute minimum for 1-2 photos
            
            if "total_volume_m3" in ai_result and float(ai_result.get("total_volume_m3", 0)) < safety_floor:
                ai_result["total_volume_m3"] = round(safety_floor, 1)
                # Ensure weight scales up proportionately (~150kg/m3)
                if "total_weight_kg" in ai_result:
                    ai_result["total_weight_kg"] = round(max(float(ai_result["total_weight_kg"]), safety_floor * 150))
                ai_result.setdefault("warnings", []).append(f"※AIの算出値が過少設計だったため、最低バッファ({safety_floor}㎥)に補正されました。")
        except Exception as e:
            print(f"OpenAI API Error: {e}")
            ai_result = None

    # モックデータフォールバック (APIキーが無い、またはエラー時)
    if not ai_result:
        # モックデータを返す
        total_vol = 1.0 * len(base64_images)
        ai_result = {
            "total_volume_m3": total_vol,
            "total_weight_kg": total_vol * 150,
            "items": [
                {"category": "テスト家具", "quantity": 1, "volume_total_m3": 0.5},
                {"category": "雑ゴミ袋", "quantity": 5, "volume_total_m3": 0.5}
            ],
            "special_disposal": {
                "recycle_items": [],
                "hard_disposal_items": [],
                "dangerous_items": []
            },
            "warnings": [
                "【モックデータ】OpenAI APIキーが設定されていないため、仮の見積もり結果を表示しています。"
            ]
        }

    # 4. 新しいJobレコードを作成（status="pending"）
    job = models.Job(
        company_id=current_user.company_id,
        user_id=current_user.id,
        job_name="【AI自動算出】名称未設定",
        total_volume_m3=ai_result.get("total_volume_m3", 0.0),
        status="pending",
        ai_result=json.dumps(ai_result, ensure_ascii=False),
        job_type="general_waste",
        pipeline_stage="estimate",
        photos=json.dumps(saved_file_urls)
    )
    # TODO: 必要であればS3などに画像を保存してURLを job.photos に保存するが今回は割愛
    
    db.add(job)
    db.commit()
    db.refresh(job)

    # 5. フロントエンドが期待するフォーマットで返却
    ai_result["job_id"] = job.job_id
    
    return ai_result
