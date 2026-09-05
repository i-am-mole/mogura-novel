(function () {
    "use strict";

    // このスクリプト自身のURLを基準にすることで、トップページでも
    // 作品ページでもサイトルートのJSONを正しく参照できる。
    const scriptUrl = document.currentScript.src;
    const metadataUrl = new URL("../update-metadata.json", scriptUrl);

    function showLoadError() {
        document.querySelectorAll("[data-site-last-updated], [data-work-metadata]")
            .forEach(function (element) {
                element.textContent = "更新情報を取得できませんでした";
            });
    }

    function applyMetadata(metadata) {
        // 全ページ共通ヘッダーの表示をJSONの日付で置き換える。
        document.querySelectorAll("[data-site-last-updated]")
            .forEach(function (element) {
                element.textContent = metadata.site_last_updated + " 更新";
            });

        // 作品一覧がないページでは、共通ヘッダーの更新だけで終了する。
        const novelList = document.querySelector(".novel-list");
        if (!novelList) {
            return;
        }

        const cards = Array.from(novelList.querySelectorAll(".novel-item"));
        cards.forEach(function (card) {
            const work = metadata.works[card.dataset.workSlug];
            const target = card.querySelector("[data-work-metadata]");
            if (!work || !target) {
                return;
            }
            target.textContent = work.last_updated + " 更新 | 全" + work.story_count
                + "話 | 合計" + work.character_count + "文字";
        });

        // HTML自体は日付に依存しない順序で生成されている。従来と同じ
        // 「更新日時が新しい作品から」の順序へ、ブラウザ上で並べ替える。
        cards.sort(function (left, right) {
            const leftWork = metadata.works[left.dataset.workSlug];
            const rightWork = metadata.works[right.dataset.workSlug];
            const leftOrder = leftWork ? leftWork.display_order : Number.MAX_SAFE_INTEGER;
            const rightOrder = rightWork ? rightWork.display_order : Number.MAX_SAFE_INTEGER;
            return leftOrder - rightOrder;
        });

        novelList.querySelectorAll(".novel-item, .separator").forEach(function (element) {
            element.remove();
        });
        cards.forEach(function (card, index) {
            novelList.appendChild(card);
            if (index < cards.length - 1) {
                const separator = document.createElement("hr");
                separator.className = "separator";
                novelList.appendChild(separator);
            }
        });
    }

    // no-cacheを指定し、HTMLが変わらない公開でも最新のJSONを再確認する。
    fetch(metadataUrl, {cache: "no-cache"})
        .then(function (response) {
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            return response.json();
        })
        .then(applyMetadata)
        .catch(function (error) {
            console.error("更新情報の読み込みに失敗しました", error);
            showLoadError();
        });
}());
