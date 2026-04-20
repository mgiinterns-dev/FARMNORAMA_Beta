document.addEventListener("DOMContentLoaded", () => {

document.querySelectorAll("form").forEach(form => {

form.addEventListener("submit", function(){

const btn = form.querySelector("button");

if(btn){
btn.innerHTML = "Processing...";
btn.style.opacity = "0.7";
}

});

});

});
