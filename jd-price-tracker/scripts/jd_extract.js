// 京东搜索结果页提取：每个商品卡 -> {sku, txt}
// 依赖新搜索页的 .plugin_goodsCardWrapper 容器（data-sku 属性）。
JSON.stringify([...document.querySelectorAll('.plugin_goodsCardWrapper')].map(c=>({sku:c.dataset.sku||'',txt:(c.innerText||'').replace(/\s+/g,'|').slice(0,400)})))
