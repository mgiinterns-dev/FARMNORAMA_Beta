document.addEventListener("DOMContentLoaded", function(){

const buttons = document.querySelectorAll("button");

buttons.forEach(btn => {

btn.addEventListener("click", function(){

btn.innerHTML = "Loading...";
btn.disabled = true;

});

});

});