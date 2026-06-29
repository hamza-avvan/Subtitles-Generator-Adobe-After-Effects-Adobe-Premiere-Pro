#target aftereffects

// Include JSON polyfill from a file in the same folder as your panel
$.evalFile(new File(File($.fileName).parent.fsName + "/JSON.jsx"));

// Helper: convert BGR integer to [R, G, B] (0-1)
function bgrToArray(colorInt) {
    var r = colorInt & 0xFF;
    var g = (colorInt >> 8) & 0xFF;
    var b = (colorInt >> 16) & 0xFF;
    return [r / 255, g / 255, b / 255];
}

function checkFilePermissions() {
    try {
        var testFile = new File(Folder.temp.fsName + "/ae_permission_test.tmp");
        testFile.open("w");
        testFile.write("test");
        testFile.close();
        testFile.remove();
        return true;
    } catch (e) {
        return false;
    }
}

function getActiveCompVideoPath() {
    try {
        var activeItem = app.project.activeItem;
        if (activeItem && activeItem instanceof CompItem) {
            // Look through layers for a footage source
            for (var i = 1; i <= activeItem.numLayers; i++) {
                var layer = activeItem.layer(i);
                if (layer.source && layer.source instanceof FootageItem && layer.source.mainSource instanceof SolidSource == false) {
                    var path = layer.source.file;
                    if (path) return path.fsName;
                }
            }
        }
    } catch (e) {}
    return ""; // not found
}

(function() {
    if (!checkFilePermissions()) {
        alert(
            "Permission denied!\n\n" +
            "After Effects is blocking file access.\n" +
            "Please go to:\n\n" +
            "  Edit → Preferences → Scripting & Expressions\n\n" +
            "and enable:\n" +
            "  ✅ Allow Scripts to Write Files and Access Network\n\n" +
            "Then restart After Effects and run this script again."
        );
        return;
    }

    var dialog = new Window("palette", "Complete Subtitle Toolkit", undefined);
    dialog.orientation = "column";
    dialog.alignChildren = ["fill","top"];
    dialog.spacing = 10;
    dialog.margins = 15;

    // ---- 1. SOURCE GROUP (video + SRT) ----
    var sourceGroup = dialog.add("panel", undefined, "Source");
    sourceGroup.orientation = "column";
    sourceGroup.alignChildren = ["fill","top"];
    sourceGroup.spacing = 6;
    sourceGroup.margins = 10;

    var videoRow = sourceGroup.add("group");
    videoRow.add("statictext", undefined, "Video:");
    var videoPath = videoRow.add("edittext", undefined, "");
    videoPath.preferredSize.width = 250;
    var videoBrowse = videoRow.add("button", undefined, "Browse...");

    var srtRow = sourceGroup.add("group");
    srtRow.add("statictext", undefined, "SRT (opt):");
    var srtPath = srtRow.add("edittext", undefined, "");
    srtPath.preferredSize.width = 250;
    var srtBrowse = srtRow.add("button", undefined, "Browse...");

    // Advanced settings (hidden by default)
    var advCheck = sourceGroup.add("checkbox", undefined, "Advanced transcription settings");
    var advGroup = sourceGroup.add("panel", undefined, "Advanced");
    advGroup.orientation = "column";
    advGroup.alignChildren = ["left","top"];
    advGroup.visible = false;
    var modelRow = advGroup.add("group");
    modelRow.add("statictext", undefined, "Whisper model:");
    var modelDropdown = modelRow.add("dropdownlist", undefined, ["tiny","base","small","medium","large"]);
    modelDropdown.selection = 1; // base
    var ffmpegRow = advGroup.add("group");
    ffmpegRow.add("statictext", undefined, "FFmpeg path:");
    var ffmpegPath = ffmpegRow.add("edittext", undefined, "ffmpeg");
    ffmpegPath.preferredSize.width = 200;
    var pythonRow = advGroup.add("group");
    pythonRow.add("statictext", undefined, "Python cmd:");
    var pythonCmd = pythonRow.add("edittext", undefined, "python");
    pythonCmd.preferredSize.width = 200;

    advCheck.onClick = function() { advGroup.visible = advCheck.value; };

    // Transcribe button
    var transcribeBtn = sourceGroup.add("button", undefined, "1. Transcribe & Align (generate JSON)");
    var transcribeProgress = sourceGroup.add("statictext", undefined, "");

    // ---- 2. STYLE GROUP (same as before) ----
    var styleGroup = dialog.add("panel", undefined, "Styling");
    styleGroup.orientation = "column";
    styleGroup.alignChildren = ["fill","top"];
    styleGroup.spacing = 6;
    styleGroup.margins = 10;

    var fontRow = styleGroup.add("group");
    fontRow.add("statictext", undefined, "Font:");
    var fontDropdown = fontRow.add("dropdownlist", undefined, ["Arial","Helvetica","Times New Roman","Courier New","Verdana","Impact","Custom..."]);
    fontDropdown.selection = 0;
    var customFontEdit = fontRow.add("edittext", undefined, "Arial");
    customFontEdit.preferredSize.width = 120;
    customFontEdit.visible = false;

    var sizeRow = styleGroup.add("group");
    sizeRow.add("statictext", undefined, "Size:");
    var sizeSlider = sizeRow.add("slider", undefined, 60, 10, 200);
    sizeSlider.preferredSize.width = 150;
    var sizeEdit = sizeRow.add("edittext", undefined, "60");
    sizeEdit.preferredSize.width = 40;

    var fillRow = styleGroup.add("group");
    fillRow.add("statictext", undefined, "Fill:");
    var fillSwatch = fillRow.add("button", undefined, "   ");
    fillSwatch.preferredSize.width = 30;
    var fillText = fillRow.add("statictext", undefined, "[1,1,1]");
    var currentFill = [1,1,1];

    var strokeRow = styleGroup.add("group");
    var strokeCheck = strokeRow.add("checkbox", undefined, "Stroke");
    strokeCheck.value = true;
    var strokeSwatch = strokeRow.add("button", undefined, "   ");
    strokeSwatch.preferredSize.width = 30;
    var strokeText = strokeRow.add("statictext", undefined, "[0,0,0]");
    var currentStroke = [0,0,0];
    strokeRow.add("statictext", undefined, "Width:");
    var strokeWidthEdit = strokeRow.add("edittext", undefined, "2");
    strokeWidthEdit.preferredSize.width = 30;

    var highlightGroup = styleGroup.add("panel", undefined, "Word Highlight");
    highlightGroup.orientation = "column";
    highlightGroup.alignChildren = ["fill","top"];
    highlightGroup.spacing = 6;
    highlightGroup.margins = 10;
    var highlightCheck = highlightGroup.add("checkbox", undefined, "Enable");
    highlightCheck.value = true;
    var hlColorRow = highlightGroup.add("group");
    hlColorRow.add("statictext", undefined, "Color:");
    var hlSwatch = hlColorRow.add("button", undefined, "   ");
    hlSwatch.preferredSize.width = 30;
    var hlText = hlColorRow.add("statictext", undefined, "[1,0.8,0,1]");
    var currentHighlight = [1,0.8,0,1];

    var posRow = styleGroup.add("group");
    posRow.add("statictext", undefined, "Vertical pos (%):");
    var posSlider = posRow.add("slider", undefined, 85, 0, 100);
    posSlider.preferredSize.width = 150;
    var posEdit = posRow.add("edittext", undefined, "85");
    posEdit.preferredSize.width = 40;

    var createBtn = dialog.add("button", undefined, "2. Create Subtitles in Comp");
    createBtn.preferredSize.height = 30;
    createBtn.enabled = false;

    // ---- State ----
    var jsonData = null;
    var jsonFilePath = null;

    // ---- Helper: run external command ----
    function runPythonTranscription() {
        var video = videoPath.text;
        var srt = srtPath.text;
        if (!video) {
            alert("Please select a video file.");
            return;
        }
        // Prepare output JSON path (same folder as video, or temp)
        var outputJson = video.replace(/\.[^.]+$/, "") + "_subtitles.json";
        var cmd = pythonCmd.text + " " +
                  '"' + File($.fileName).parent.fsName + '/generate_subtitle_json.py' + '"' +
                  ' "' + video + '"' +
                  ' -o "' + outputJson + '"' +
                  ' --model ' + modelDropdown.selection.text;
        if (srt) {
            cmd += ' --srt "' + srt + '"';
        }
        if (ffmpegPath.text !== "ffmpeg") {
            cmd += ' --ffmpeg "' + ffmpegPath.text + '"';
        }
        transcribeProgress.text = "Processing... (this may take a few minutes)";
        dialog.update();

        // Call system
        var result = system.callSystem(cmd);
        try {
            var result = system.callSystem(cmd);
        } catch (e) {
            alert("Command failed: " + e.toString());
            return;
        }

        // After completion
        transcribeProgress.text = "Done.";
        // Load JSON
        var file = new File(outputJson);
        if (file.exists) {
            file.open('r');
            var content = file.read();
            // $.writeln(content);
            try {
                jsonData = JSON.parse(content);
                jsonFilePath = outputJson;
                createBtn.enabled = true;
                alert("Transcription completed. Ready to create subtitles.");
            } catch (e) {
                alert("Error parsing JSON: " + e.toString());   
            }
        } else {
            alert("JSON file not created. Check console for errors.");
        }
    }

    // ---- Styling UI logic (similar to previous) ----
    function updatePreview() {
        // Not implemented here for brevity, but can be added as before
    }

    // ---- Create comp function (unchanged) ----
    function createSubtitles() {
        if (!jsonData) {
            alert("No JSON data. Run transcription first.");
            return;
        }
        var fontName = fontDropdown.selection.text == "Custom..." ? customFontEdit.text : fontDropdown.selection.text;
        var fontSize = parseInt(sizeEdit.text) || 60;
        var useStroke = strokeCheck.value;
        var strokeWidth = parseInt(strokeWidthEdit.text) || 2;
        var highlightEnabled = highlightCheck.value;
        var vertPos = parseInt(posEdit.text) / 100;
        var compDuration = jsonData.duration;

        app.beginUndoGroup("Create Subtitles");
        var comp = app.project.items.addComp("Subtitles", 1920, 1080, 1, compDuration, 30);
        // var bg = comp.layers.addSolid([0,0,0], "Background", comp.width, comp.height, 1);
        // bg.inPoint = 0;
        // bg.outPoint = compDuration;

        for (var i = 0; i < jsonData.subtitles.length; i++) {
            var sub = jsonData.subtitles[i];
            if (sub.text.replace(/^\s+|\s+$/g, "") === "") continue;
            var layer = comp.layers.addText(sub.text);
            layer.inPoint = sub.start;
            layer.outPoint = sub.end;

            var textProp = layer.property("Source Text");
            var textDoc = textProp.value;
            textDoc.font = fontName;
            textDoc.fontSize = fontSize;
            textDoc.fillColor = currentFill;
            if (useStroke) {
                textDoc.strokeColor = currentStroke;
                textDoc.strokeWidth = strokeWidth;
            } else {
                textDoc.strokeColor = [0,0,0];
                textDoc.strokeWidth = 0;
            }
            textDoc.justification = ParagraphJustification.CENTER_JUSTIFY;
            textProp.setValue(textDoc);

            var yPos = Math.round(1080 * vertPos);
            layer.property("Position").setValue([960, yPos]);

            if (highlightEnabled && sub.words && sub.words.length > 0) {
                // =====================================================
                // TEXT GROUPS
                // =====================================================

                var textProps = layer.property("ADBE Text Properties");
                var animatorGroup = textProps.property("ADBE Text Animators");

                // Create animator
                var animator = animatorGroup.addProperty("ADBE Text Animator");

                // =====================================================
                // FILL COLOR
                // =====================================================

                var animatorProps = animator.property("ADBE Text Animator Properties");

                var fillColor = animatorProps.addProperty("ADBE Text Fill Color");

                fillColor.setValue(currentHighlight);

                // =====================================================
                // RANGE SELECTOR
                // =====================================================

                var selectors = animator.property("ADBE Text Selectors");

                var selector = selectors.addProperty("ADBE Text Selector");

                // Advanced settings
                var advanced = selector.property("ADBE Text Range Advanced");

                // Units = INDEX
                // 1 = Percentage
                // 2 = Index
                advanced.property("ADBE Text Range Units").setValue(2);

                // Based On = WORDS
                // 1 = Characters
                // 2 = Characters Excluding Spaces
                // 3 = Words
                // 4 = Lines
                advanced.property("ADBE Text Range Type2").setValue(3);

                // Smoothness = 0
                advanced.property("ADBE Text Selector Smoothness").setValue(0);

                // =====================================================
                // INDEX PROPERTIES
                // =====================================================

                var startProp = selector.property("ADBE Text Index Start");
                var endProp   = selector.property("ADBE Text Index End");

                if (!startProp || !endProp) {
                    throw new Error("Could not access Index Start/End properties.");
                }

                // =====================================================
                // INITIAL STATE
                // =====================================================

                startProp.setValueAtTime(sub.start, 0);
                endProp.setValueAtTime(sub.start, 0);

                startProp.setInterpolationTypeAtKey(
                    1,
                    KeyframeInterpolationType.HOLD
                );

                endProp.setInterpolationTypeAtKey(
                    1,
                    KeyframeInterpolationType.HOLD
                );

                // =====================================================
                // WORD-BY-WORD HIGHLIGHT
                // =====================================================

                for (var w = 0; w < sub.words.length; w++) {

                    var word = sub.words[w];

                    var t = word.start;

                    // AE indexes are 1-based
                    var index = w + 1;

                    // Highlight ONE word
                    startProp.setValueAtTime(t, index -1);
                    endProp.setValueAtTime(t, index);

                    // Convert keyframes to HOLD
                    var sKey = startProp.nearestKeyIndex(t);
                    var eKey = endProp.nearestKeyIndex(t);

                    startProp.setInterpolationTypeAtKey(
                        sKey,
                        KeyframeInterpolationType.HOLD
                    );

                    endProp.setInterpolationTypeAtKey(
                        eKey,
                        KeyframeInterpolationType.HOLD
                    );
                }

                // =====================================================
                // CLEAR HIGHLIGHT AFTER LAST WORD
                // =====================================================

                var lastWordEnd = sub.words[sub.words.length - 1].end;

                if (sub.end > lastWordEnd + 0.02) {

                    startProp.setValueAtTime(sub.end, 0);
                    endProp.setValueAtTime(sub.end, 0);

                    var lastS = startProp.nearestKeyIndex(sub.end);
                    var lastE = endProp.nearestKeyIndex(sub.end);

                    startProp.setInterpolationTypeAtKey(
                        lastS,
                        KeyframeInterpolationType.HOLD
                    );

                    endProp.setInterpolationTypeAtKey(
                        lastE,
                        KeyframeInterpolationType.HOLD
                    );
                }
            }
        }
        app.endUndoGroup();
        alert("Done!");
    }

    // ---- Event bindings ----
    videoPath.text = getActiveCompVideoPath();
    videoBrowse.onClick = function() {
        var f = File.openDialog("Select video file", "*.mp4;*.mov;*.avi;*.mkv");
        if (f) videoPath.text = f.fsName;
    };
    srtBrowse.onClick = function() {
        var f = File.openDialog("Select SRT file", "*.srt");
        if (f) srtPath.text = f.fsName;
    };
    transcribeBtn.onClick = runPythonTranscription;
    createBtn.onClick = createSubtitles;
    fontDropdown.onChange = function() {
        customFontEdit.visible = (fontDropdown.selection.text == "Custom...");
    };
    sizeSlider.onChanging = function() { sizeEdit.text = Math.round(sizeSlider.value); };
    posSlider.onChanging = function() { posEdit.text = Math.round(posSlider.value); };

    // Fill color
    fillSwatch.onClick = function() {
        var c = $.colorPicker(currentFill);
        if (c !== undefined) {
            currentFill = bgrToArray(c);
            fillText.text = "[" + currentFill[0].toFixed(2) + "," + currentFill[1].toFixed(2) + "," + currentFill[2].toFixed(2) + "]";
        }
    };

    // Stroke color
    strokeSwatch.onClick = function() {
        var c = $.colorPicker(currentStroke);
        if (c !== undefined) {
            currentStroke = bgrToArray(c);
            strokeText.text = "[" + currentStroke[0].toFixed(2) + "," + currentStroke[1].toFixed(2) + "," + currentStroke[2].toFixed(2) + "]";
        }
    };

    // Highlight color (keep alpha from previous version)
    hlSwatch.onClick = function() {
        var c = $.colorPicker(currentHighlight.slice(0, 3)); // pass RGB only
        if (c !== undefined) {
            var rgb = bgrToArray(c);
            currentHighlight[0] = rgb[0];
            currentHighlight[1] = rgb[1];
            currentHighlight[2] = rgb[2];
            // alpha remains unchanged
            hlText.text = "[" + currentHighlight[0].toFixed(2) + "," +
                    currentHighlight[1].toFixed(2) + "," +
                    currentHighlight[2].toFixed(2) + "," +
                    currentHighlight[3].toFixed(2) + "]";
        }
    };


    dialog.show();
})();