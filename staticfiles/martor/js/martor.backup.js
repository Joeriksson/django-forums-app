/**
 * Name         : Martor v1.4.8
 * Created by   : Agus Makmun (Summon Agus)
 * Release date : 18-Mar-2020
 * License      : GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007
 * Repository   : https://github.com/agusmakmun/django-markdown-editor
**/

(function ($) {
    if (!$) {
        $ = django.jQuery;
    }
    $.fn.martor = function() {
        $('.martor').trigger('martor.init');

        var getCookie = function(name) {
            var cookieValue = null;
            var i = 0;
            if (document.cookie && document.cookie !== '') {
                var cookies = document.cookie.split(';');
                for (i; i < cookies.length; i++) {
                    var cookie = jQuery.trim(cookies[i]);
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
        };

        this.each(function(i, obj) {
            var mainMartor   = $(obj);
            var field_name   = mainMartor.data('field-name');
            var textareaId   = $('#id_'+field_name);
            var editorId     = 'martor-'+field_name;
            var editor       = ace.edit(editorId);
            var editorConfig = JSON.parse(textareaId.data('enable-configs').replace(/'/g, '"'));

            editor.setTheme('ace/theme/github');
            editor.getSession().setMode('ace/mode/markdown');
            editor.getSession().setUseWrapMode(true);
            editor.$blockScrolling = Infinity;
            editor.renderer.setScrollMargin(10, 10);
            editor.setAutoScrollEditorIntoView(true);
            editor.setShowPrintMargin(false);
            editor.setOptions({
                enableBasicAutocompletion: true,
                enableSnippets: true,
                enableLiveAutocompletion: true,
                enableMultiselect: false
            });

            if (editorConfig.living == 'true') {
                $(obj).addClass('enable-living');
            }

            var emojiWordCompleter = {
                getCompletions: function(editor, session, pos, prefix, callback) {
                    var wordList = typeof(emojis) != "undefined" ? emojis : [];
                    var obj = editor.getSession().getTokenAt(pos.row, pos.column.count);
                    var curTokens = obj.value.split(/\s+/);
                    var lastToken = curTokens[curTokens.length-1];

                    if (lastToken[0] == ':') {
                      callback(null, wordList.map(function(word) {
                          return {
                              caption: word,
                              value: word.replace(':', '') + ' ',
                              meta: 'emoji'
                          };
                      }));
                    }
                }
            }
            var mentionWordCompleter = {
                getCompletions: function(editor, session, pos, prefix, callback) {
                    var obj = editor.getSession().getTokenAt(pos.row, pos.column.count);
                    var curTokens = obj.value.split(/\s+/);
                    var lastToken = curTokens[curTokens.length-1];

                    if (lastToken[0] == '@' && lastToken[1] == '[') {
                        username = lastToken.replace(/([\@\[/\]/])/g, '');
                        $.ajax({
                            url: textareaId.data('search-users-url'),
                            data: {
                                'username': username,
                                'csrfmiddlewaretoken': getCookie('csrftoken')
                            },
                            success: function(data) {
                                if (data['status'] == 200) {
                                    var wordList = [];
                                    for (var i = 0; i < data['data'].length; i++) {
                                        wordList.push(data['data'][i].username)
                                    }
                                    callback(null, wordList.map(function(word) {
                                        return {
                                            caption: word,
                                            value: word,
                                            meta: 'username'
                                        };
                                    }));
                                }
                            }
                        });
                    }
                }
            }

            if (editorConfig.mention === 'true') {
                editor.completers = [emojiWordCompleter, mentionWordCompleter]
            }else {
                editor.completers = [emojiWordCompleter]
            }

            textareaId.attr({'style': 'display:none'});

            $(obj).find('.martor-toolbar').find('.markdown-selector').attr({'data-field-name': field_name});
            $(obj).find('.upload-progress').attr({'data-field-name': field_name});
            $(obj).find('.modal-help-guide').attr({'data-field-name': field_name});
            $(obj).find('.modal-emoji').attr({'data-field-name': field_name});

            editor.on('change', function(evt){
                var value = editor.getValue();
                textareaId.val(value);
            });

            $('#'+editorId).resizable({
                direction: 'bottom',
                stop: function() {
                    editor.resize();
                }
            });

            var currentTab = $('.tab.segment[data-tab=preview-tab-'+field_name+']');
            var previewTabButton = $('.item[data-tab=preview-tab-'+field_name+']');
            var refreshPreview = function() {
                var value = textareaId.val();
                var form = new FormData();
                form.append('content', value);
                form.append('csrfmiddlewaretoken', getCookie('csrftoken'));
                currentTab.addClass('martor-preview-stale');

                $.ajax({
                    url: textareaId.data('markdownfy-url'),
                    type: 'POST',
                    data: form,
                    processData: false,
                    contentType: false,
                    success: function(response) {
                        if (response) {
                            currentTab.html(response).removeClass('martor-preview-stale');

                            $(document).trigger('martor:preview', [currentTab]);

                            if (editorConfig.hljs == 'true') {
                                $('pre').each(function (i, block) {
                                    hljs.highlightBlock(block);
                                });
                            }
                        } else {
                            currentTab.html('<p>Nothing to preview</p>');
                        }
                    },
                    error: function(response) {
                        console.log("error", response);
                    }
                });
            };

            refreshPreview();

            if (editorConfig.living !== 'true') {
              previewTabButton.click(function(){
                  $(this).closest('.tab-martor-menu').find('.martor-toolbar').hide();
                  refreshPreview();
              });
            }else {
              editor.on('change', refreshPreview);
            }

            var editorTabButton = $('.item[data-tab=editor-tab-'+field_name+']');
            editorTabButton.click(function(){
                $(this).closest('.tab-martor-menu').find('.martor-toolbar').show();
            });

            if (editorConfig.spellcheck == 'true') {
              try {
                enable_spellcheck(editorId);
              }catch (e) {
                console.log("Spellcheck lib doesn't installed.");
              }
            }

            var markdownToBold = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, ' **** ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row, curpos.column+3);
                }else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '**'+text+'**');
                  originalRange.end.column += 4;
                  editor.focus();
                  editor.selection.setSelectionRange(originalRange);
                }
            };

            var markdownToItalic = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, ' __ ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row, curpos.column+2);
                }else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '_'+text+'_');
                  originalRange.end.column += 2;
                  editor.focus();
                  editor.selection.setSelectionRange(originalRange);
                }
            };

            var markdownToUnderscores = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, ' ++++ ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row, curpos.column+3);
                }else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '++'+text+'++');
                  originalRange.end.column += 4;
                  editor.focus();
                  editor.selection.setSelectionRange(originalRange);
                }
            };

            var markdownToStrikethrough = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, ' ~~~~ ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row, curpos.column+3);
                }else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '~~'+text+'~~');
                  originalRange.end.column += 4;
                  editor.focus();
                  editor.selection.setSelectionRange(originalRange);
                }
            };

            var markdownToHorizontal = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, '\n\n----------\n\n');
                    editor.focus();
                    editor.selection.moveTo(curpos.row+4, curpos.column+10);
                }
                else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '\n\n----------\n\n'+text);
                  editor.focus();
                  editor.selection.moveTo(
                      originalRange.end.row+4,
                      originalRange.end.column+10
                  );
                }
            };

            var markdownToH1 = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, '\n\n# ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row+2, curpos.column+2);
                }
                else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '\n\n# '+text+'\n');
                  editor.focus();
                  editor.selection.moveTo(
                      originalRange.end.row+2,
                      originalRange.end.column+2
                  );
                }
            };

            var markdownToH2 = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, '\n\n## ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row+2, curpos.column+3);
                }
                else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '\n\n## '+text+'\n');
                  editor.focus();
                  editor.selection.moveTo(
                      originalRange.end.row+2,
                      originalRange.end.column+3
                  );
                }
            };

            var markdownToH3 = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, '\n\n### ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row+2, curpos.column+4);
                }
                else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '\n\n### '+text+'\n');
                  editor.focus();
                  editor.selection.moveTo(
                      originalRange.end.row+2,
                      originalRange.end.column+4
                  );
                }
            };

            var markdownToPre = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, '\n\n```\n\n```\n');
                    editor.focus();
                    editor.selection.moveTo(curpos.row+3, curpos.column);
                }
                else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '\n\n```\n'+text+'\n```\n');
                  editor.focus();
                  editor.selection.moveTo(
                      originalRange.end.row+3,
                      originalRange.end.column+3
                  );
                }
            };

            var markdownToCode = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, ' `` ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row, curpos.column+2);
                }else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '`'+text+'`');
                  originalRange.end.column += 2;
                  editor.focus();
                  editor.selection.setSelectionRange(originalRange);
                }
            };

            var markdownToBlockQuote = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, '\n\n> \n');
                    editor.focus();
                    editor.selection.moveTo(curpos.row+2, curpos.column+2);
                }
                else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '\n\n> '+text+'\n');
                  editor.focus();
                  editor.selection.moveTo(
                      originalRange.end.row+2,
                      originalRange.end.column+2
                  );
                }
            };

            var markdownToUnorderedList = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, '\n\n* ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row+2, curpos.column+2);
                }
                else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '\n\n* '+text);
                  editor.focus();
                  editor.selection.moveTo(
                      originalRange.end.row+2,
                      originalRange.end.column+2
                  );
                }
            };

            var markdownToOrderedList = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, '\n\n1. ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row+2, curpos.column+3);
                }
                else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '\n\n1. '+text);
                  editor.focus();
                  editor.selection.moveTo(
                      originalRange.end.row+2,
                      originalRange.end.column+3
                  );
                }
            };

            var markdownToLink = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, ' [](http://) ');
                    editor.focus();
                    editor.selection.moveTo(curpos.row, curpos.column+2);
                }else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '['+text+'](http://) ');
                  editor.focus();
                  editor.selection.moveTo(
                      originalRange.end.row,
                      originalRange.end.column+10
                  );
                }
            };

            var markdownToImageLink = function(editor, imageData) {
                var originalRange = editor.getSelectionRange();
                if (typeof(imageData) === 'undefined') {
                    if (editor.selection.isEmpty()) {
                        var curpos = editor.getCursorPosition();
                        editor.session.insert(curpos, ' ![](http://) ');
                        editor.focus();
                        editor.selection.moveTo(curpos.row, curpos.column+3);
                    }else {
                        var range = editor.getSelectionRange();
                        var text = editor.session.getTextRange(range);
                        editor.session.replace(range, '!['+text+'](http://) ');
                        editor.focus();
                        editor.selection.moveTo(
                            originalRange.end.row,
                            originalRange.end.column+11
                        );
                    }
                }else {
                  var curpos = editor.getCursorPosition();
                  editor.session.insert(curpos, '!['+imageData.name+']('+imageData.link+') ');
                  editor.focus();
                  editor.selection.moveTo(
                      curpos.row,
                      curpos.column+imageData.name.length+2
                  );
                }
            };

            var markdownToMention = function(editor) {
                var originalRange = editor.getSelectionRange();
                if (editor.selection.isEmpty()) {
                    var curpos = editor.getCursorPosition();
                    editor.session.insert(curpos, ' @[]');
                    editor.focus();
                    editor.selection.moveTo(curpos.row, curpos.column+3);
                }else {
                  var range = editor.getSelectionRange();
                  var text = editor.session.getTextRange(range);
                  editor.session.replace(range, '@['+text+']');
                  editor.focus();
                  editor.selection.moveTo(
                      originalRange.end.row,
                      originalRange.end.column+3
                  )
                }
            };

            var markdownToEmoji = function(editor, data_target) {
                var curpos = editor.getCursorPosition();
                editor.session.insert(curpos, ' '+data_target+' ');
                editor.focus();
                editor.selection.moveTo(curpos.row, curpos.column+data_target.length+2);
            };

            var markdownToUploadImage = function(editor) {
                var firstForm = $('#'+editorId).closest('form').get(0);
                var field_name = editor.container.id.replace('martor-', '');
                var form = new FormData(firstForm);
                form.append('csrfmiddlewaretoken', getCookie('csrftoken'));

                $.ajax({
                    url: textareaId.data('upload-url'),
                    type: 'POST',
                    data: form,
                    async: true,
                    cache: false,
                    contentType: false,
                    enctype: 'multipart/form-data',
                    processData: false,
                    beforeSend: function() {
                        console.log('Uploading...');
                        $('.upload-progress[data-field-name='+field_name+']').show();
                    },
                    success: function (response) {
                        $('.upload-progress[data-field-name='+field_name+']').hide();
                        if (response.status == 200) {
                            console.log(response);
                            markdownToImageLink(
                              editor=editor,
                              imageData={name: response.name, link: response.link}
                            );
                        }else {
                          alert(response.error);
                        }
                    },
                    error: function(response) {
                        console.log("error", response);
                        $('.upload-progress[data-field-name='+field_name+']').hide();
                    }
                });
                return false;
            };

            editor.commands.addCommand({
                name: 'markdownToBold',
                bindKey: {win: 'Ctrl-B', mac: 'Command-B'},
                exec: function(editor) {
                    markdownToBold(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToItalic',
                bindKey: {win: 'Ctrl-I', mac: 'Command-I'},
                exec: function(editor) {
                    markdownToItalic(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToUnderscores',
                bindKey: {win: 'Ctrl-Shift-U', mac: 'Command-Option-U'},
                exec: function(editor) {
                    markdownToUnderscores(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToStrikethrough',
                bindKey: {win: 'Ctrl-Shift-S', mac: 'Command-Option-S'},
                exec: function(editor) {
                    markdownToStrikethrough(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToHorizontal',
                bindKey: {win: 'Ctrl-H', mac: 'Command-H'},
                exec: function(editor) {
                    markdownToHorizontal(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToH1',
                bindKey: {win: 'Ctrl-Alt-1', mac: 'Command-Option-1'},
                exec: function(editor) {
                    markdownToH1(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToH2',
                bindKey: {win: 'Ctrl-Alt-2', mac: 'Command-Option-3'},
                exec: function(editor) {
                    markdownToH2(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToH3',
                bindKey: {win: 'Ctrl-Alt-3', mac: 'Command-Option-3'},
                exec: function(editor) {
                    markdownToH3(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToPre',
                bindKey: {win: 'Ctrl-Alt-P', mac: 'Command-Option-P'},
                exec: function(editor) {
                    markdownToPre(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToCode',
                bindKey: {win: 'Ctrl-Alt-C', mac: 'Command-Option-C'},
                exec: function(editor) {
                    markdownToCode(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToBlockQuote',
                bindKey: {win: 'Ctrl-Q', mac: 'Command-Q'},
                exec: function(editor) {
                    markdownToBlockQuote(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToUnorderedList',
                bindKey: {win: 'Ctrl-U', mac: 'Command-U'},
                exec: function(editor) {
                    markdownToUnorderedList(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToOrderedList',
                bindKey: {win: 'Ctrl-Shift+O', mac: 'Command-Option-O'},
                exec: function(editor) {
                    markdownToOrderedList(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToLink',
                bindKey: {win: 'Ctrl-L', mac: 'Command-L'},
                exec: function(editor) {
                    markdownToLink(editor);
                },
                readOnly: true
            });
            editor.commands.addCommand({
                name: 'markdownToImageLink',
                bindKey: {win: 'Ctrl-Shift-I', mac: 'Command-Option-I'},
                exec: function(editor) {
                    markdownToImageLink(editor);
                },
                readOnly: true
            });
            if (editorConfig.mention === 'true') {
                editor.commands.addCommand({
                    name: 'markdownToMention',
                    bindKey: {win: 'Ctrl-M', mac: 'Command-M'},
                    exec: function(editor) {
                        markdownToMention(editor);
                    },
                    readOnly: true
                });
            }

            $('.markdown-bold[data-field-name='+field_name+']').click(function(){
                markdownToBold(editor);
            });
            $('.markdown-italic[data-field-name='+field_name+']').click(function(){
                markdownToItalic(editor);
            });
            $('.markdown-horizontal[data-field-name='+field_name+']').click(function(){
                markdownToHorizontal(editor);
            });
            $('.markdown-h1[data-field-name='+field_name+']').click(function(){
                markdownToH1(editor);
            });
            $('.markdown-h2[data-field-name='+field_name+']').click(function(){
                markdownToH2(editor);
            });
            $('.markdown-h3[data-field-name='+field_name+']').click(function(){
                markdownToH3(editor);
            });
            $('.markdown-pre[data-field-name='+field_name+']').click(function(){
                markdownToPre(editor);
            });
            $('.markdown-code[data-field-name='+field_name+']').click(function(){
                markdownToCode(editor);
            });
            $('.markdown-blockquote[data-field-name='+field_name+']').click(function(){
                markdownToBlockQuote(editor);
            });
            $('.markdown-unordered-list[data-field-name='+field_name+']').click(function(){
                markdownToUnorderedList(editor);
            });
            $('.markdown-ordered-list[data-field-name='+field_name+']').click(function(){
                markdownToOrderedList(editor);
            });
            $('.markdown-link[data-field-name='+field_name+']').click(function(){
                markdownToLink(editor);
            });
            $('.markdown-image-link[data-field-name='+field_name+']').click(function(){
                markdownToImageLink(editor);
            });

            var btnMention = $('.markdown-direct-mention[data-field-name='+field_name+']');
            var btnUpload = $('.markdown-image-upload[data-field-name='+field_name+']');
            if (editorConfig.mention === 'true' && editorConfig.imgur === 'true') {
                btnMention.click(function(){
                    markdownToMention(editor);
                });
                btnUpload.on('change', function(evt){
                    evt.preventDefault();
                    markdownToUploadImage(editor);
                });
            }else if (editorConfig.mention === 'true' && editorConfig.imgur === 'false') {
                btnMention.click(function(){
                    markdownToMention(editor);
                });
                btnUpload.remove();
            }else if (editorConfig.mention === 'false' && editorConfig.imgur === 'true') {
                btnMention.remove();
                btnUpload.on('change', function(evt){
                    evt.preventDefault();
                    markdownToUploadImage(editor);
                });
            }
            else {
                btnMention.remove();
                btnUpload.remove();
                $('.markdown-reference tbody tr')[1].remove();
            }

            $('.markdown-help[data-field-name='+field_name+']').click(function(){
                $('.modal-help-guide[data-field-name='+field_name+']').modal('show');
            });

            mainMartor.find('.ui.martor-toolbar .ui.dropdown').dropdown();
            mainMartor.find('.ui.tab-martor-menu .item').tab();

            var martorField       = $('.martor-field-'+field_name);
            var btnToggleMaximize = $('.markdown-toggle-maximize[data-field-name='+field_name+']');

            var handleToggleMinimize = function() {
                $(document.body).removeClass('overflow');
                $(this).attr({'title': 'Full Screen'});
                $(this).find('.minimize.icon').removeClass('minimize').addClass('maximize');
                $('.main-martor-fullscreen').find('.martor-preview').removeAttr('style');
                mainMartor.removeClass('main-martor-fullscreen');
                martorField.removeAttr('style');
                editor.resize();
            }
            var handleToggleMaximize = function(selector) {
                selector.attr({'title': 'Minimize'});
                selector.find('.maximize.icon').removeClass('maximize').addClass('minimize');
                mainMartor.addClass('main-martor-fullscreen');

                var clientHeight = document.body.clientHeight-90;
                martorField.attr({'style':'height:'+clientHeight+'px'});

                var preview = $('.main-martor-fullscreen').find('.martor-preview');
                preview.attr({'style': 'overflow-y: auto;height:'+clientHeight+'px'});

                editor.resize();
                selector.one('click', handleToggleMinimize);
                $(document.body).addClass('overflow');
            }
            btnToggleMaximize.on('click', function(){
                handleToggleMaximize($(this));
            });

            $(document).keyup(function(e) {
              if (e.keyCode == 27 && mainMartor.hasClass('main-martor-fullscreen')) {
                $('.minimize.icon').trigger('click');
              }
            });

            $('.markdown-emoji[data-field-name='+field_name+']').click(function(){
                var modalEmoji = $('.modal-emoji[data-field-name='+field_name+']');
                var emojiList = typeof(emojis) != "undefined" ? emojis : [];
                var segmentEmoji = modalEmoji.find('.emoji-content-body');
                var loaderInit  = modalEmoji.find('.emoji-loader-init');

                segmentEmoji.html('');
                loaderInit.show();
                modalEmoji.modal({
                    onVisible: function () {
                        for (var i = 0; i < emojiList.length; i++) {
                            var linkEmoji = textareaId.data('base-emoji-url') + emojiList[i].replace(/:/g, '') + '.png';
                            segmentEmoji.append(''
                                +'<div class="four wide column">'
                                + '<p><a data-emoji-target="'+emojiList[i]+'" class="insert-emoji">'
                                + '<img class="marked-emoji" src="'+linkEmoji+'"> '+emojiList[i]
                                + '</a></p>'
                                +'</div>');
                            $('a[data-emoji-target="'+emojiList[i]+'"]').click(function(){
                                markdownToEmoji(editor, $(this).data('emoji-target'));
                                modalEmoji.modal('hide', 100);
                            });
                        }
                        loaderInit.hide();
                        modalEmoji.modal('refresh');
                    }
                }).modal('show');
            });

            if (textareaId.val() != '') {
                editor.setValue(textareaId.val(), -1);
            }
        });
    };

    $(function() {
        $('.main-martor').martor();
    });

    if ('django' in window && 'jQuery' in window.django)
        django.jQuery(document).on('formset:added', function (event, $row) {
            $row.find('.main-martor').each(function () {
                var id = $row.attr('id');
                id = id.substr(id.lastIndexOf('-') + 1);
                var fixed = $(this.outerHTML.replace(/__prefix__/g, id));
                $(this).replaceWith(fixed);
                fixed.martor();
            });
        });
})(jQuery);
