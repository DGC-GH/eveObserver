function copyToClipboard(text) {
    // Create a temporary textarea element
    var textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);

    // Select and copy the text
    textArea.focus();
    textArea.select();

    try {
        var successful = document.execCommand('copy');
        if (successful) {
            // Show a brief success message
            showCopyMessage('Copied to clipboard!');
        } else {
            showCopyMessage('Copy failed');
        }
    } catch (err) {
        console.error('Copy failed:', err);
        showCopyMessage('Copy failed');
    }

    // Remove the temporary element
    document.body.removeChild(textArea);
}

function showCopyMessage(message) {
    // Remove any existing message
    var existingMsg = document.getElementById('eve-copy-message');
    if (existingMsg) {
        existingMsg.remove();
    }

    // Create and show the message
    var msg = document.createElement('div');
    msg.id = 'eve-copy-message';
    msg.innerText = message;
    msg.style.position = 'fixed';
    msg.style.top = '20px';
    msg.style.right = '20px';
    msg.style.backgroundColor = '#0073aa';
    msg.style.color = 'white';
    msg.style.padding = '10px 15px';
    msg.style.borderRadius = '4px';
    msg.style.zIndex = '9999';
    msg.style.fontSize = '14px';
    msg.style.boxShadow = '0 2px 5px rgba(0,0,0,0.3)';

    document.body.appendChild(msg);

    // Remove the message after 2 seconds
    setTimeout(function() {
        if (msg.parentNode) {
            msg.parentNode.removeChild(msg);
        }
    }, 2000);
}