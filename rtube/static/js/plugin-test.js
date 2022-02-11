function test() {
    var testButton = createButton("&#128013;")

    var playbackRate = document.querySelector(".vjs-playback-rate");
    insertAfter(testButton, playbackRate);

    function insertAfter(newElement, element)
    {
        element.parentNode.insertBefore(newElement, element.nextSibling);
    }

    function createButton(icon) {
        var button = document.createElement("button");
        button.classList.add("vjs-menu-button");
        button.innerHTML = icon;
        button.style.fontSize = "1.8em";
        return button;
    }
}

videojs.registerPlugin("test", test);
