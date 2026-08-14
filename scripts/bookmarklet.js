/**
 * 大海浮光 AIGC - 全平台商品信息提取器 (Bookmarklet)
 * 
 * 使用方法：
 * 1. 复制全部代码
 * 2. 在浏览器新建书签，URL 粘贴此代码
 * 3. 打开任意电商商品页面（京东/淘宝/天猫/Amazon/拼多多等）
 * 4. 点击书签 → 自动提取商品信息并复制到剪贴板
 * 5. 粘贴到 AIGC 工作台的「手动输入」区域
 */

javascript:(function(){
  var d=document;
  var info={url:location.href,title:d.title,product_name:"",price:"",images:[],description:"",selling_points:[],specs:{},raw_text:""};

  // 1. 商品名称
  var nameSelectors=['.sku-name','.title-name','.product-name','h1[data-spm]','.ProductMeta__Title','#productTitle','.tb-main-title','[data-testid="product-title"]','h1'];
  for(var i=0;i<nameSelectors.length;i++){
    var el=d.querySelector(nameSelectors[i]);
    if(el){info.product_name=el.innerText.trim();break;}
  }

  // 2. 价格
  var priceSelectors=['.p-price .price','.price-value','.tb-rmb-num','.a-price .a-offscreen','[data-testid="price"]','.current-price'];
  for(var i=0;i<priceSelectors.length;i++){
    var el=d.querySelector(priceSelectors[i]);
    if(el){info.price=el.innerText.trim();break;}
  }

  // 3. 图片
  var imgs=d.querySelectorAll('img[src*="img"]');
  imgs.forEach(function(img){
    var src=img.src||img.getAttribute('data-src')||img.getAttribute('data-lazy-img')||'';
    if(src&&src.startsWith('http')&&!src.includes('icon')&&!src.includes('avatar')&&!src.includes('logo')&&info.images.length<9){
      info.images.push(src);
    }
  });

  // 4. 描述/卖点
  var descEl=d.querySelector('meta[name="description"]')||d.querySelector('meta[property="og:description"]');
  if(descEl)info.description=descEl.getAttribute('content')||'';

  // 5. 页面文本（取前 5000 字符）
  var bodyText=d.body.innerText||'';
  info.raw_text=bodyText.replace(/\n{3,}/g,'\n\n').trim().substring(0,5000);

  // 6. 复制到剪贴板
  var json=JSON.stringify(info,null,2);
  navigator.clipboard.writeText(json).then(function(){
    var box=d.createElement('div');
    box.style.cssText='position:fixed;top:20px;right:20px;z-index:99999;background:#14141a;color:#7ed5a7;padding:14px 20px;border-radius:10px;font:13px/1.5 monospace;max-width:380px;box-shadow:0 12px 40px rgba(0,0,0,.35)';
    box.innerHTML='<b>✅ 已复制商品信息</b><br><small>'+info.product_name.substring(0,50)+'</small><br><small style="color:#aeb5c1">'+info.images.length+' 张图 · '+info.raw_text.length+' 字</small><br><small style="color:#78b6ff;margin-top:6px">粘贴到 AIGC 工作台「手动输入」区域</small>';
    d.body.appendChild(box);
    setTimeout(function(){box.remove();},4000);
  }).catch(function(){
    alert('复制失败，请手动选择下方文本：\n\n'+json);
  });
})();
