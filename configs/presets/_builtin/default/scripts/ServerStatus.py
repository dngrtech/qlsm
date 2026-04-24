import sys
	
def printRichFormat(serverName, serverState):
    serverHealth=''
    serverName=serverName.ljust(20)
    if serverState == "RUNNING":
        serverHealth =  serverName + '\033[1;32m' + serverState + '\033[0m'
    elif serverState == "STARTING":
        serverHealth = serverName + '\033[1;33m' + serverState + '\033[0m'
    elif serverState == "UNKNOWN":
        serverHealth = serverName + '\033[1;34m' + serverState + '\033[0m'
    else:
        serverHealth = serverName + '\033[1;31m' + serverState + '\033[0m'
    serverHealth= '# '+ serverHealth.ljust(61) + '#\n'
    return serverHealth
	
def printFormat(serverName, serverState):
    serverHealth=''
    serverName=serverName.ljust(20)
    if serverState == "RUNNING":
        serverHealth =  serverName +  serverState 
    elif serverState == "STARTING":
        serverHealth = serverName +  serverState 
    elif serverState == "UNKNOWN":
        serverHealth = serverName +  serverState 
    else:
        serverHealth = serverName +  serverState 
    serverHealth= '# '+ serverHealth.ljust(50) + '#\n'
    return serverHealth
	
def serverStatus(url,ports,formatType,username,password):
    serverstat = '############          ' + url + '          #############\n'
    portArr=ports.split(',')
    for port in portArr:
        try:	
            connect(username,password,'t3://'+url+':'+port)
            serverNames = cmo.getServers()
            domainRuntime()
            print 'Fetching state of every WebLogic instance'
            #Fetch the state of the every WebLogic instance		
            for name in serverNames:
                cd("/ServerLifeCycleRuntimes/" + name.getName())
                serverState = cmo.getState()
                if formatType == "cmd":
                    serverstat = serverstat + printFormat(name.getName(),serverState)
                elif formatType == "conEmu":
				    serverstat = serverstat + printRichFormat(name.getName(),serverState)
        except:
            serverstat = serverstat + '__________________________________________________\n'
            serverstat = serverstat + '|'.ljust(50)+'|\n'
            serverstat = serverstat + '|'.ljust(50)+'|\n'
            serverstat = serverstat + '|'.ljust(50)+'|\n'
            serverstat = serverstat + '|'.ljust(50)+'|\n'
            serverstat = serverstat + '|'.ljust(15)+ (url+  ':'+port+' is down').ljust(35)+ '|\n'
            serverstat = serverstat + '|'.ljust(50)+'|\n'
            serverstat = serverstat + '|'.ljust(50)+'|\n'
            serverstat = serverstat + '|'.ljust(50)+'|\n'
            serverstat = serverstat + '|'.ljust(50)+'|\n'
            serverstat = serverstat + '__________________________________________________\n'
    serverstat = serverstat +'#####################################################\n'
    serverstat = serverstat +'#####################################################\n'
    return serverstat



	
result=''
result = result + serverStatus(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5])
print result