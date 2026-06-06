import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import UM 1.5 as UM

UM.Dialog
{
    id: zaaSettingsDialog
    title: "Z Anti-Aliasing Settings"
    width: 400
    height: 380
    minimumWidth: 400
    minimumHeight: 380

    property var preferences: UM.Application.preferences

    ColumnLayout
    {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        CheckBox
        {
            id: enabledCheckbox
            text: "Enable Z Anti-Aliasing"
            checked: preferences.getValue("zaa/enabled")
            onCheckedChanged: preferences.setValue("zaa/enabled", checked)
        }

        GroupBox
        {
            title: "Parameters"
            Layout.fillWidth: true
            enabled: enabledCheckbox.checked

            ColumnLayout
            {
                anchors.fill: parent
                spacing: 8

                RowLayout
                {
                    Label { text: "Max contour depth (mm):" ; Layout.preferredWidth: 180 }
                    SpinBox
                    {
                        id: maxContourSpinbox
                        from: 0
                        to: 2000
                        stepSize: 50
                        value: Math.round(preferences.getValue("zaa/max_contour") * 1000)
                        onValueChanged: preferences.setValue("zaa/max_contour", value / 1000.0)

                        textFromValue: function(value) { return (value / 1000.0).toFixed(3) + " mm"; }
                        valueFromText: function(text) { return Math.round(parseFloat(text) * 1000); }
                    }
                }

                Label
                {
                    text: "0 = auto (half of layer height)"
                    font.italic: true
                    color: "#888"
                }

                RowLayout
                {
                    Label { text: "Resolution (mm):" ; Layout.preferredWidth: 180 }
                    SpinBox
                    {
                        id: resolutionSpinbox
                        from: 100
                        to: 2000
                        stepSize: 100
                        value: Math.round(preferences.getValue("zaa/resolution") * 1000)
                        onValueChanged: preferences.setValue("zaa/resolution", value / 1000.0)

                        textFromValue: function(value) { return (value / 1000.0).toFixed(1) + " mm"; }
                        valueFromText: function(text) { return Math.round(parseFloat(text) * 1000); }
                    }
                }
            }
        }

        GroupBox
        {
            title: "Target Regions"
            Layout.fillWidth: true
            enabled: enabledCheckbox.checked

            ColumnLayout
            {
                anchors.fill: parent
                spacing: 4

                CheckBox
                {
                    id: topSurfaceCheck
                    text: "TOP-SURFACE-SKIN (recommended)"
                    checked: preferences.getValue("zaa/target_types").indexOf("TOP-SURFACE-SKIN") >= 0
                }
                CheckBox
                {
                    id: skinCheck
                    text: "SKIN"
                    checked: preferences.getValue("zaa/target_types").indexOf("SKIN") >= 0
                            && preferences.getValue("zaa/target_types").indexOf("TOP-SURFACE-SKIN") < 0
                            ? preferences.getValue("zaa/target_types").indexOf("SKIN") >= 0
                            : false
                }
                CheckBox
                {
                    id: wallOuterCheck
                    text: "WALL-OUTER"
                    checked: preferences.getValue("zaa/target_types").indexOf("WALL-OUTER") >= 0
                }
            }
        }

        CheckBox
        {
            id: collisionCheckbox
            text: "Enable collision detection"
            checked: preferences.getValue("zaa/enable_collision")
            onCheckedChanged: preferences.setValue("zaa/enable_collision", checked)
            enabled: enabledCheckbox.checked
        }

        Item { Layout.fillHeight: true }

        RowLayout
        {
            Layout.alignment: Qt.AlignRight
            spacing: 8

            Button
            {
                text: "OK"
                onClicked:
                {
                    // Build target types string
                    var types = [];
                    if (topSurfaceCheck.checked) types.push("TOP-SURFACE-SKIN");
                    if (skinCheck.checked) types.push("SKIN");
                    if (wallOuterCheck.checked) types.push("WALL-OUTER");
                    preferences.setValue("zaa/target_types", types.join(","));

                    zaaSettingsDialog.accept();
                }
            }

            Button
            {
                text: "Cancel"
                onClicked: zaaSettingsDialog.reject()
            }
        }
    }
}
