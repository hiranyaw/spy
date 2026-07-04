// ═══════════════════════════════════════════════════════════════════════
// PASTE THIS INTO BROWSER CONSOLE TO LOAD THE PINE SCRIPT
// Press F12, go to Console tab, paste this entire script, press Enter
// ═══════════════════════════════════════════════════════════════════════

(async function() {
    console.log("Starting Pine Script loader...");

    // Fetch the Pine script file content
    const response = await fetch('file:///C:/Users/Hiranya/spy/hiranya_spy_edge_tracker_v1.0.pine');
    if (!response.ok) {
        console.error("Could not load Pine script file");
        return;
    }

    const pineCode = await response.text();
    console.log(`Loaded Pine script: ${pineCode.length} characters`);

    // Step 1: Open Pine Editor
    console.log("Looking for Pine Editor button...");
    const allButtons = document.querySelectorAll('button, [role="button"], [class*="Button"]');

    let pineButton = null;
    for (const btn of allButtons) {
        const text = (btn.innerText || btn.textContent || '').toLowerCase();
        if (text.includes('pine') && (text.includes('editor') || text.includes('script'))) {
            pineButton = btn;
            break;
        }
    }

    if (!pineButton) {
        // Try keyboard shortcut
        console.log("Pine button not found, trying Alt+P shortcut");
        const event = new KeyboardEvent('keydown', {
            altKey: true,
            key: 'p',
            code: 'KeyP'
        });
        document.dispatchEvent(event);
        await new Promise(r => setTimeout(r, 1500));
    } else {
        console.log("Clicking Pine Editor button");
        pineButton.click();
        await new Promise(r => setTimeout(r, 1500));
    }

    // Step 2: Click "New" button
    console.log("Looking for New button...");
    await new Promise(r => setTimeout(r, 500));

    const newButtons = Array.from(document.querySelectorAll('button, [role="button"]'))
        .filter(b => {
            const text = (b.innerText || b.textContent || '').trim();
            return text === 'New' || (text.includes('New') && !text.includes('Not'));
        });

    if (newButtons.length > 0) {
        console.log(`Found ${newButtons.length} New buttons, clicking the first one`);
        newButtons[0].click();
        await new Promise(r => setTimeout(r, 1500));
    } else {
        console.log("No New button found");
    }

    // Step 3: Find the code editor
    console.log("Looking for code editor...");
    await new Promise(r => setTimeout(r, 1000));

    let codeEditor = null;

    // Try different selectors for the editor
    const selectors = [
        'textarea[class*="editor"]',
        'div[contenteditable="true"][class*="editor"]',
        '.cm-editor textarea', // CodeMirror
        '.CodeMirror textarea',
        'textarea[class*="pine"]',
        'textarea[class*="code"]',
        'textarea:not([style*="display: none"])'
    ];

    for (const selector of selectors) {
        const editors = document.querySelectorAll(selector);
        if (editors.length > 0) {
            codeEditor = editors[0];
            console.log(`Found code editor with selector: ${selector}`);
            break;
        }
    }

    if (!codeEditor) {
        // Try to find any visible textarea
        const allTextareas = document.querySelectorAll('textarea');
        for (const ta of allTextareas) {
            if (getComputedStyle(ta).display !== 'none' && getComputedStyle(ta).visibility !== 'hidden') {
                codeEditor = ta;
                console.log("Found visible textarea");
                break;
            }
        }
    }

    if (codeEditor) {
        console.log("Pasting Pine Script code...");
        codeEditor.focus();

        // Clear existing content
        if (codeEditor.value !== undefined) {
            codeEditor.value = '';
        }

        // Paste the script
        if (codeEditor.value !== undefined) {
            codeEditor.value = pineCode;
        } else {
            // For contenteditable divs
            codeEditor.innerHTML = '';
            codeEditor.textContent = pineCode;
        }

        // Trigger input events
        codeEditor.dispatchEvent(new Event('input', { bubbles: true }));
        codeEditor.dispatchEvent(new Event('change', { bubbles: true }));
        codeEditor.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }));

        console.log("✓ Pine Script pasted successfully!");
        console.log("\nNext steps:");
        console.log("1. Review the script in the editor");
        console.log("2. Click 'Save' and give it a name: 'Hiranya SPY Edge Tracker v1.0'");
        console.log("3. Click 'Add to Chart' to apply it");

        return { status: "success", charactersLoaded: pineCode.length };
    } else {
        console.error("Code editor not found!");
        return { status: "error", message: "Could not find code editor" };
    }
})().then(result => {
    console.log("Result:", result);
}).catch(error => {
    console.error("Error:", error);
});
