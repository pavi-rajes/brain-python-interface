%module pcidio
%{
extern unsigned char init(char* dev);
extern unsigned char closeall();
extern unsigned char sendMsg(char* msg);
extern unsigned int register_sys(char* name, char* dtype);
extern unsigned char sendData(unsigned char idx, char* data);
extern unsigned char sendRow(unsigned char idx, unsigned int row);
%}
extern unsigned char init(char* dev);
extern unsigned char closeall();
extern unsigned char sendMsg(char* msg);
extern unsigned int register_sys(char* name, char* dtype);
extern unsigned char sendData(unsigned char idx, char* data);
extern unsigned char sendRow(unsigned char idx, unsigned int row);