// JARVIS Orbit - Complete Features Module
// Adds: Command Palette, Zoom, Bookmarks, Toast, Sessions, HUD, Vertical Tabs, Print/Screenshot
(function() {
var d = document;
function $(s) { return d.querySelector(s); }
var NL = String.fromCharCode(10);
var $toastContainer = d.getElementById("toastContainer");
function showToast(type, title, msg, dur) {
  dur = dur || 4000;
  var icons = {ok: "✓", warn: "⚠", err: "✗", info: "ℹ"};
  var t = d.createElement("div"); t.className = "toast";
  var html = "<div class=\"toast-icon "+type+"\">"+title+"</div>";
  html += "<div class=\"toast-body\"><div class=\"toast-title\">"+title+"</div>";
  if(msg) html += "<div class=\"toast-msg\">"+msg+"</div>";
  html += "</div><button class=\"toast-close\">×</button>";
  t.innerHTML = html;
  if($toastContainer) $toastContainer.appendChild(t);
  t.querySelector(".toast-close").onclick = function(){ t.classList.add("out"); setTimeout(function(){ t.remove(); },200); };
  setTimeout(function(){ t.classList.add("out"); setTimeout(function(){ t.remove(); },200); },dur);
}

// COMMAND PALETTE (Ctrl+K)
var CMD_ITEMS = [
  {l:"New Tab",d:"Open new tab",s:"Ctrl+T",i:"+",a:function(){createTab()}},
  {l:"Close Tab",d:"Close current",s:"Ctrl+W",i:"x",a:function(){if(activeTabId)closeTab(activeTabId)}},
  {l:"Reload",d:"Refresh page",s:"Ctrl+R",i:"r",a:function(){try{webview.reload()}catch(e){}}},
  {l:"Find on Page",d:"Search text",s:"Ctrl+F",i:"f",a:function(){toggleFind()}},
  {l:"Settings",d:"Browser settings",i:"s",a:function(){navigateTo("orbit://settings")}},
  {l:"History",d:"Browsing history",i:"h",a:function(){navigateTo("orbit://history")}},
  {l:"Downloads",d:"View downloads",i:"d",a:function(){navigateTo("orbit://downloads")}},
  {l:"Bookmarks",d:"View bookmarks",i:"b",a:function(){navigateTo("orbit://bookmarks")}},
  {l:"Tasks",d:"Agent tasks",i:"t",a:function(){navigateTo("orbit://tasks")}},
  {l:"Memory",d:"Saved memories",i:"m",a:function(){navigateTo("orbit://memory")}},
  {l:"Diagnostics",d:"System status",i:"i",a:function(){navigateTo("orbit://diagnostics")}},
  {l:"Print Page",d:"Print current page",s:"Ctrl+P",i:"p",a:function(){printPage()}},
  {l:"Screenshot",d:"Capture page",s:"Ctrl+Shift+S",i:"c",a:function(){takeScreenshot()}},
  {l:"Zoom In",d:"Increase zoom",s:"Ctrl+=",i:"+",a:function(){zoomIn()}},
  {l:"Zoom Out",d:"Decrease zoom",s:"Ctrl+-",i:"-",a:function(){zoomOut()}},
  {l:"Toggle Sidebar",d:"Show/hide JARVIS",s:"Ctrl+Shift+J",i:"j",a:function(){jarvisBtn.click()}},
];

var cmdIdx=0;var cmdFiltered=[];
function openCmdPalette(){var bg=document.getElementById("cmdPaletteBg");var inp=document.getElementById("cmdInput");if(!bg)return;bg.classList.add("on");inp.value="";cmdIdx=0;filterCmd("");setTimeout(function(){inp.focus()},50);}
function closeCmdPalette(){var bg=document.getElementById("cmdPaletteBg");if(bg)bg.classList.remove("on");}
function filterCmd(q){q=(q||"").toLowerCase().trim();cmdFiltered=[];var res=document.getElementById("cmdResults");if(!res)return;var html="";
if(q){for(var[id,tab]of tabs){if(tab.title.toLowerCase().indexOf(q)>=0||tab.url.toLowerCase().indexOf(q)>=0){cmdFiltered.push({l:tab.title,d:tab.url,i:"T",a:function(tid){return function(){activateTab(tid)}}(id)});}}}
CMD_ITEMS.forEach(function(c){if(!q||c.l.toLowerCase().indexOf(q)>=0||c.d.toLowerCase().indexOf(q)>=0){cmdFiltered.push(c);}});
if(cmdFiltered.length){html+="<div class=cmd-group-label>Results</div>";}
cmdFiltered.forEach(function(c,i){html+="<div class=cmd-item data-ci="+i+"><div class=cmd-item-icon>"+c.i+"</div><div class=cmd-item-label>"+c.l+"<div class=cmd-item-desc>"+c.d+"</div></div>"+(c.s?"<div class=cmd-item-shortcut>"+c.s+"</div>":"")+"</div>";});
res.innerHTML=html;res.querySelectorAll(".cmd-item").forEach(function(el){el.addEventListener("click",function(){var idx=parseInt(el.getAttribute("data-ci"));if(cmdFiltered[idx]){cmdFiltered[idx].a();closeCmdPalette();}});});}

// ZOOM CONTROLS
var currentZoom = 1.0;
var zoomLevels = JSON.parse(localStorage.getItem("orbit-zoom") || "{}");
function getZoomDomain(){try{var t=tabs.get(activeTabId);return t?new URL(t.url).hostname:"";}catch(e){return "";}}
function zoomIn(){setZoom(currentZoom+0.1);}
function zoomOut(){setZoom(currentZoom-0.1);}
function zoomReset(){setZoom(1.0);}
function setZoom(level){currentZoom=Math.max(0.25,Math.min(5.0,level));var dom=getZoomDomain();if(dom){zoomLevels[dom]=currentZoom;localStorage.setItem("orbit-zoom",JSON.stringify(zoomLevels));}var zi=document.getElementById("zoomIndicator");if(zi)zi.textContent=Math.round(currentZoom*100)+"%";if(webview)webview.setZoomFactor(currentZoom);}

// BOOKMARK BAR
var bookmarks = JSON.parse(localStorage.getItem("orbit-bookmarks") || "[]");
function renderBookmarkBar(){var bar=document.getElementById("bookmarkBar");if(!bar)return;var addBtn=bar.querySelector(".bm-add");var sep=bar.querySelector(".bm-sep");bar.innerHTML="";if(addBtn)bar.appendChild(addBtn);if(sep)bar.appendChild(sep);bookmarks.forEach(function(bm,i){var el=document.createElement("button");el.className="bm-item";el.innerHTML="<svg width=12 height=12 viewBox=0 0 12 12 fill=none><circle cx=6 cy=6 r=4.5 stroke=currentColor/></svg>"+bm.title;el.title=bm.url;el.addEventListener("click",function(){navigateTo(bm.url)});el.addEventListener("contextmenu",function(e){e.preventDefault();if(confirm("Remove: "+bm.title+"?")){bookmarks.splice(i,1);localStorage.setItem("orbit-bookmarks",JSON.stringify(bookmarks));renderBookmarkBar();}});bar.appendChild(el);});}
function addBookmark(){var tab=tabs.get(activeTabId);if(!tab)return;var title=prompt("Bookmark name:",tab.title);if(!title)return;bookmarks.push({title:title,url:tab.url});localStorage.setItem("orbit-bookmarks",JSON.stringify(bookmarks));renderBookmarkBar();showToast("ok","Bookmark Added",title);}
var $omniStar=document.getElementById("omniStar");if($omniStar)$omniStar.addEventListener("click",addBookmark);var $bmAdd=document.getElementById("bmAddBtn");if($bmAdd)$bmAdd.addEventListener("click",addBookmark);

// SESSION MANAGEMENT
function saveSession(){var s=[];tabs.forEach(function(tab,id){s.push({id:id,url:tab.url,title:tab.title,agentOwned:tab.agentOwned});});localStorage.setItem("orbit-session",JSON.stringify({tabs:s,activeTabId:activeTabId,savedAt:Date.now()}));}
function restoreSession(){try{var data=JSON.parse(localStorage.getItem("orbit-session"));if(!data||!data.tabs||!data.tabs.length)return false;data.tabs.forEach(function(t){createTab(t.url);});if(data.activeTabId&&tabs.has(data.activeTabId))activateTab(data.activeTabId);showToast("ok","Session Restored",data.tabs.length+" tabs recovered");return true;}catch(e){return false;}}

// PERFORMANCE HUD
function updatePerfHud(){var jd=document.getElementById("perfJarvisDot");var jl=document.getElementById("perfJarvis");var tl=document.getElementById("perfTabs");var zl=document.getElementById("perfZoom");if(jd)jd.className="perf-dot "+(jarvisOnline?"ok":"off");if(jl)jl.textContent="JARVIS: "+(jarvisOnline?"ON":"OFF");if(tl)tl.textContent=tabs.size+" tab"+(tabs.size!==1?"s":"");if(zl)zl.textContent=Math.round(currentZoom*100)+"%";}
var $perfHud=document.getElementById("perfHud");if($perfHud)$perfHud.addEventListener("click",function(){navigateTo("orbit://diagnostics")});

// VERTICAL TABS
var verticalTabs = false;
var tabStripVertical = document.getElementById("tabStripVertical");
function toggleVerticalTabs(){verticalTabs=!verticalTabs;if(tabStripVertical)tabStripVertical.classList.toggle("on",verticalTabs);tabStrip.parentElement.style.display=verticalTabs?"none":"";showToast("info",verticalTabs?"Vertical Tabs":"Horizontal Tabs",verticalTabs?"Tab strip moved to left":"Tab strip moved to top");}
function renderVerticalTabs(){if(!tabStripVertical)return;tabStripVertical.innerHTML="";tabs.forEach(function(tab,id){var el=document.createElement("button");el.className="tab"+(id===activeTabId?" active":"")+(tab.agentOwned?" agent-owned":"");el.dataset.id=id;el.innerHTML="<span class=tab-title>"+tab.title+"</span><span class=tab-close data-close="+id+">x</span>";el.addEventListener("click",function(e){var closeBtn=e.target.closest("[data-close]");if(closeBtn){e.stopPropagation();closeTab(closeBtn.dataset.close);return;}activateTab(id);});tabStripVertical.appendChild(el);});}

// PRINT and SCREENSHOT
function printPage(){try{if(webview&&!webview.classList.contains("hidden"))webview.print();}catch(e){showToast("err","Print Failed",e.message);}}
function takeScreenshot(){try{if(webview&&!webview.classList.contains("hidden")){webview.capturePage().then(function(image){var dataUrl=image.toDataURL();var a=document.createElement("a");a.href=dataUrl;a.download="orbit-screenshot-"+Date.now()+".png";a.click();showToast("ok","Screenshot Saved","Downloaded to default folder");});}}catch(e){showToast("err","Screenshot Failed",e.message);}}

// KEYBOARD SHORTCUTS
document.addEventListener("keydown",function(e){var ctrl=e.ctrlKey||e.metaKey;
if(ctrl&&e.key.toLowerCase()==="k"){e.preventDefault();openCmdPalette();return;}
if(ctrl&&e.shiftKey&&e.key.toLowerCase()==="b"){e.preventDefault();var bar=document.getElementById("bookmarkBar");if(bar)bar.classList.toggle("hidden");return;}
if(ctrl&&e.key.toLowerCase()==="="){e.preventDefault();zoomIn();return;}
if(ctrl&&e.key==="-"){e.preventDefault();zoomOut();return;}
if(ctrl&&e.key==="0"){e.preventDefault();zoomReset();return;}
if(ctrl&&e.key.toLowerCase()==="p"){e.preventDefault();printPage();return;}
if(ctrl&&e.shiftKey&&e.key.toLowerCase()==="s"){e.preventDefault();takeScreenshot();return;}
if(ctrl&&e.key.toLowerCase()==="h"){e.preventDefault();navigateTo("orbit://history");return;}
if(ctrl&&e.key.toLowerCase()==="j"){e.preventDefault();navigateTo("orbit://downloads");return;}
if(ctrl&&e.key.toLowerCase()==="d"){e.preventDefault();addBookmark();return;}
});

// CMD PALETTE EVENT LISTENERS
var cmdBg=document.getElementById("cmdPaletteBg");var cmdInp=document.getElementById("cmdInput");if(cmdBg)cmdBg.addEventListener("click",function(e){if(e.target===cmdBg)closeCmdPalette();});
if(cmdInp){cmdInp.addEventListener("input",function(){cmdIdx=0;filterCmd(cmdInp.value);});
cmdInp.addEventListener("keydown",function(e){
if(e.key==="ArrowDown"){e.preventDefault();cmdIdx=Math.min(cmdIdx+1,cmdFiltered.length-1);filterCmd(cmdInp.value);}
if(e.key==="ArrowUp"){e.preventDefault();cmdIdx=Math.max(cmdIdx-1,0);filterCmd(cmdInp.value);}
if(e.key==="Enter"){e.preventDefault();if(cmdFiltered[cmdIdx]){cmdFiltered[cmdIdx].a();closeCmdPalette();}}
if(e.key==="Escape")closeCmdPalette();});}

// ZOOM INDICATOR CLICK
var $zi=document.getElementById("zoomIndicator");if($zi)$zi.addEventListener("click",function(){var input=prompt("Zoom level (25-500):",Math.round(currentZoom*100));if(input){var val=parseFloat(input);if(!isNaN(val))setZoom(val/100);}});

// SAVE SESSION ON NAVIGATION
var origNav=navigateTo;
navigateTo=function(url){origNav(url);saveSession();setTimeout(updatePerfHud,200);};

// CLOSE: SAVE SESSION
window.addEventListener("beforeunload",function(){saveSession();});

// INIT
renderBookmarkBar();updatePerfHud();
showToast("info","JARVIS Orbit","Press Ctrl+K for command palette");
console.log("[ORBIT] Features module loaded");
})();
