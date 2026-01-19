<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width" />
  <title>3 LED Pattern Control</title>
  <style>
    body { background-color: rgb(212,250,252); font-family: Arial; text-align: center; }
    .red { background-color: red; width: 12em; height: 4em; font-size: 20px; color: white; border: none; margin: 10px; cursor: pointer; }
    .box { background: #fff; margin: 20px auto; padding: 15px; max-width: 820px; border-radius: 10px; text-align: left; }
    pre { white-space: pre-wrap; }
  </style>
</head>

<body>
<h1>LED Pattern (Continuous Forward & Reverse)</h1>

<form method="get" action="index1.php">
  <input class="red" type="submit" value="START PATTERN" name="on">
  <input class="red" type="submit" value="STOP (ALL OFF)" name="off">
</form>

<?php
  $ctl = "/usr/local/bin/ledpattern_ctl";
  $logFile = "/tmp/led_pattern.log";

  if (isset($_GET['on'])) {
    $out = trim(shell_exec("sudo -n $ctl start 2>&1"));
    echo "<div class='box'><b>Start output:</b><pre>" . htmlspecialchars($out) . "</pre></div>";
  }

  if (isset($_GET['off'])) {
    $out = trim(shell_exec("sudo -n $ctl stop 2>&1"));
    echo "<div class='box'><b>Stop output:</b><pre>" . htmlspecialchars($out) . "</pre></div>";
  }

  $status = trim(shell_exec("sudo -n $ctl status 2>&1"));
  echo "<div class='box'><b>Service Status:</b> " . htmlspecialchars($status) . "<hr>";

  $tail = shell_exec("tail -n 30 " . escapeshellarg($logFile) . " 2>/dev/null");
  if (trim($tail) !== "") {
    echo "<b>Last log lines:</b><pre>" . htmlspecialchars($tail) . "</pre>";
  } else {
    echo "<b>Log:</b> (empty / not created yet) " . htmlspecialchars($logFile);
  }
  echo "</div>";
?>
</body>
</html>
