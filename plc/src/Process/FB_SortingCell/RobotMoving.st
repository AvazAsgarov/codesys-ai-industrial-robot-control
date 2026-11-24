// TRUE while a robot motion command is active (for the HMI).
METHOD RobotMoving : BOOL

RobotMoving := fbRobot.xMoving;
